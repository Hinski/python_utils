/*
 * split_ts_data_to_hourly.c
 *
 * Splittet ts_data-Dateien in einstündige Dateien (gleiche Logik wie
 * split_ts_data_to_hourly.py). Zwei-Pass, speichereffizient.
 *
 * - Stündliche Dateien werden kontinuierlich geschrieben (Puffer 500 Zeilen → Flush).
 * - Resume: Bereits verarbeitete Quelldateien stehen in <Ausgabeordner>/.split_hourly_progress.
 *   Bei Abbruch und Neustart werden nur noch nicht verarbeitete Dateien gelesen.
 *
 * Kompilieren (macOS/Linux):
 *   cc -O2 -o split_ts_data_to_hourly split_ts_data_to_hourly.c
 *   oder: make -f Makefile.split_hourly
 *
 * Verwendung:
 *   ./split_ts_data_to_hourly [quell_ordner] [ziel_ordner]
 *   Ohne Argumente: SOURCE_DIR und OUTPUT_DIR (siehe #define).
 */

#define _POSIX_C_SOURCE 200809L
#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <ctype.h>
#include <dirent.h>
#include <sys/stat.h>
#include <errno.h>

#ifndef SOURCE_DIR_DEFAULT
#define SOURCE_DIR_DEFAULT "/Volumes/Extreme SSD/Gorigo/ts_data"
#endif
#ifndef OUTPUT_DIR_DEFAULT
#define OUTPUT_DIR_DEFAULT "/Volumes/Extreme SSD/Gorigo/ts_data_hourly"
#endif

#define WRITE_BUFFER_SIZE  2000   /* Größer = weniger Flush, schneller */
#define SORT_CHUNK_SIZE    100000
#define READ_BUF_SIZE      (1*1024*1024)   /* 1 MB Lese-Puffer pro Datei */
#define WRITE_BUF_SIZE     (512*1024)     /* 512 KB Schreib-Puffer */
#define LINE_BUF_INIT      4096
#define MAX_PATH           2048
#define NBUCKETS           16384
#define MAX_LINE           65536
#define TEXT_SAMPLE_SIZE   8192
#define MAX_BINARY_RATIO   0.05
#define PROGRESS_FILENAME  ".split_hourly_progress"

/* Tag-im-Jahr aus (Jahr, Monat, Tag) ohne Zeitzone. */
static int day_of_year(int Y, int m, int d) {
    static const int days[] = {0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334};
    int leap = (Y % 4 == 0 && (Y % 100 != 0 || Y % 400 == 0));
    int doy = days[m - 1] + d;
    if (m > 2) doy += leap;
    return doy;
}

/* Schnelles Parsen der ersten Spalte ohne sscanf: "YYYY-MM-DD HH:MM:SS" (fixe Länge 19).
 * Optional Anführungszeichen davor. Liefert 1 bei Erfolg, 0 sonst.
 */
static int parse_first_field_fast(const char *line, int *yy, int *ddd, int *HHMM) {
    const char *p = line;
    while (*p == ' ' || *p == '\t' || *p == '"') p++;
    /* Mindestens "YYYY-MM-DD HH:MM" = 16 Zeichen */
    if (!isdigit((unsigned char)p[0]) || !isdigit((unsigned char)p[1]) || !isdigit((unsigned char)p[2]) || !isdigit((unsigned char)p[3]))
        return 0;
    if (p[4] != '-' || p[7] != '-' || p[10] != ' ' || p[13] != ':')
        return 0;
    int Y = (p[0]-'0')*1000 + (p[1]-'0')*100 + (p[2]-'0')*10 + (p[3]-'0');
    int m = (p[5]-'0')*10 + (p[6]-'0');
    int d = (p[8]-'0')*10 + (p[9]-'0');
    int H = (p[11]-'0')*10 + (p[12]-'0');
    int M = (p[14]-'0')*10 + (p[15]-'0');
    if (m < 1 || m > 12 || d < 1 || d > 31 || H < 0 || H > 23 || M < 0 || M > 59)
        return 0;
    *yy = (Y % 100);
    *ddd = day_of_year(Y, m, d);
    *HHMM = H * 100 + M;
    return 1;
}

/* Parst erste Spalte zu einem int64-Sortierschlüssel (YYYYMMDDHHMMSSmmm).
 * Schneller als strncmp in Pass 2. Liefert 1 bei Erfolg, 0 sonst.
 */
static int parse_to_sort_key(const char *line, long long *key_out) {
    const char *p = line;
    while (*p == ' ' || *p == '\t' || *p == '"') p++;
    if (!isdigit((unsigned char)p[0]) || !isdigit((unsigned char)p[1]) || !isdigit((unsigned char)p[2]) || !isdigit((unsigned char)p[3]))
        return 0;
    if (p[4] != '-' || p[7] != '-' || p[10] != ' ' || p[13] != ':')
        return 0;
    long long Y = (p[0]-'0')*1000LL + (p[1]-'0')*100 + (p[2]-'0')*10 + (p[3]-'0');
    int m = (p[5]-'0')*10 + (p[6]-'0');
    int d = (p[8]-'0')*10 + (p[9]-'0');
    int H = (p[11]-'0')*10 + (p[12]-'0');
    int M = (p[14]-'0')*10 + (p[15]-'0');
    int S = 0, ms = 0;
    if (p[16] == ':' && isdigit((unsigned char)p[17]) && isdigit((unsigned char)p[18])) {
        S = (p[17]-'0')*10 + (p[18]-'0');
        if (S < 0 || S > 59) return 0;
        if (p[19] == '.') {
            if (isdigit((unsigned char)p[20])) ms = (p[20]-'0')*100;
            if (isdigit((unsigned char)p[21])) ms += (p[21]-'0')*10;
            if (isdigit((unsigned char)p[22])) ms += (p[22]-'0');
        }
    }
    if (m < 1 || m > 12 || d < 1 || d > 31 || H < 0 || H > 23 || M < 0 || M > 59)
        return 0;
    *key_out = Y * 10000000000000LL + (long long)m * 100000000000LL + (long long)d * 1000000000LL
             + (long long)H * 10000000LL + (long long)M * 100000LL + (long long)S * 1000LL + ms;
    return 1;
}

/* Heuristik: Sieht die Datei nach Text aus? Liest erste TEXT_SAMPLE_SIZE Bytes.
 * Zu viele NUL/Steuerzeichen (außer Tab, LF, CR) → Binär (return 0). */
static int is_likely_text_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    unsigned char buf[TEXT_SAMPLE_SIZE];
    size_t n = fread(buf, 1, sizeof buf, f);
    fclose(f);
    if (n == 0) return 1;
    size_t binary = 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char b = buf[i];
        if (b == 0 || (b < 32 && b != 9 && b != 10 && b != 13))
            binary++;
    }
    return (binary * 100 <= n * (int)(MAX_BINARY_RATIO * 100));
}

/* TOA5-Header überspringen: erste Zeile lesen; wenn TOA5, 3 weitere Zeilen lesen. */
static int skip_toa5_header(FILE *f) {
    char *line = NULL;
    size_t cap = 0;
    if (getline(&line, &cap, f) <= 0) { free(line); return 0; }
    const char *s = line;
    while (*s == ' ' || *s == '\t' || (unsigned char)*s == 0xEF) s++; /* BOM */
    if (strncmp(s, "TOA5", 4) == 0 || (s[0] == '"' && strncmp(s+1, "TOA5", 4) == 0)) {
        for (int i = 0; i < 3; i++) { if (getline(&line, &cap, f) <= 0) break; }
    }
    free(line);
    return 1;
}

/* Dateiname für Stunde: gor_yy_ddd_HHMM.dat */
static void hour_filename(char *buf, size_t size, int yy, int ddd, int HHMM) {
    snprintf(buf, size, "gor_%02d_%03d_%04d.dat", yy, ddd, HHMM);
}

/* --- Hash-Bucket für Pass 1 --- */
typedef struct line_node {
    char *line;
    struct line_node *next;
} line_node_t;

typedef struct bucket {
    int yy, ddd, HHMM;
    line_node_t *head;
    size_t count;
    struct bucket *next;
} bucket_t;

static bucket_t *ht[NBUCKETS];

static unsigned bucket_key(int yy, int ddd, int HHMM) {
    return (unsigned)(yy * 100000 + ddd * 1000 + HHMM) % NBUCKETS;
}

static bucket_t *find_or_create_bucket(int yy, int ddd, int HHMM) {
    unsigned idx = bucket_key(yy, ddd, HHMM);
    for (bucket_t *b = ht[idx]; b; b = b->next)
        if (b->yy == yy && b->ddd == ddd && b->HHMM == HHMM)
            return b;
    bucket_t *b = calloc(1, sizeof(bucket_t));
    if (!b) return NULL;
    b->yy = yy; b->ddd = ddd; b->HHMM = HHMM;
    b->next = ht[idx];
    ht[idx] = b;
    return b;
}

static void bucket_append(bucket_t *b, const char *line) {
    line_node_t *n = malloc(sizeof(line_node_t));
    if (!n) return;
    n->line = strdup(line);
    n->next = b->head;
    b->head = n;
    b->count++;
}

static void flush_bucket(bucket_t *b, const char *output_dir) {
    if (!b || b->count == 0) return;
    char path[MAX_PATH];
    hour_filename(path, sizeof path, b->yy, b->ddd, b->HHMM);
    char full[MAX_PATH];
    snprintf(full, sizeof full, "%s/%s", output_dir, path);
    FILE *out = fopen(full, "a");
    if (!out) {
        fprintf(stderr, "Kann nicht öffnen zum Schreiben: %s\n", full);
        return;
    }
    setvbuf(out, NULL, _IOFBF, WRITE_BUF_SIZE);
    for (line_node_t *n = b->head; n; n = n->next) {
        fputs(n->line, out);
        if (n->line[strlen(n->line)-1] != '\n') fputc('\n', out);
    }
    fclose(out);
    /* Liste leeren, Knoten freigeben */
    while (b->head) {
        line_node_t *t = b->head;
        b->head = t->next;
        free(t->line);
        free(t);
    }
    b->count = 0;
}

static void flush_all_buckets(const char *output_dir) {
    for (int i = 0; i < NBUCKETS; i++)
        for (bucket_t *b = ht[i]; b; b = b->next)
            flush_bucket(b, output_dir);
}

static void free_all_buckets(void) {
    for (int i = 0; i < NBUCKETS; i++) {
        bucket_t *b = ht[i];
        while (b) {
            bucket_t *next = b->next;
            while (b->head) {
                line_node_t *t = b->head;
                b->head = t->next;
                free(t->line);
                free(t);
            }
            free(b);
            b = next;
        }
        ht[i] = NULL;
    }
}

/* Zeile ohne abschließendes \n trimmen; Leerzeilen überspringen. */
static char *trim_line(char *line) {
    size_t n = strlen(line);
    while (n > 0 && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = '\0';
    char *p = line;
    while (*p == ' ' || *p == '\t') p++;
    if (!*p) return NULL;
    return line;
}

/* Pass 1: Quellverzeichnis durchgehen, Zeilen parsen, nach Stunde puffern und schreiben. */
static unsigned long pass1_stream_append(const char *source_dir, const char *output_dir) {
    DIR *dir = opendir(source_dir);
    if (!dir) {
        fprintf(stderr, "Quellordner kann nicht geöffnet werden: %s\n", source_dir);
        return 0;
    }
    mkdir(output_dir, 0755);
    memset(ht, 0, sizeof ht);

    struct dirent *ent;
    char **dat_files = NULL;
    size_t num_files = 0, cap_files = 0;
    while ((ent = readdir(dir)) != NULL) {
        if (ent->d_name[0] == '.' && (ent->d_name[1] == '\0' || (ent->d_name[1] == '_'))) continue;
        size_t len = strlen(ent->d_name);
        if (len < 5 || strcmp(ent->d_name + len - 4, ".dat") != 0) continue;
        if (num_files >= cap_files) {
            cap_files = cap_files ? cap_files * 2 : 64;
            char **t = realloc(dat_files, cap_files * sizeof(char*));
            if (!t) break;
            dat_files = t;
        }
        dat_files[num_files] = strdup(ent->d_name);
        if (dat_files[num_files]) num_files++;
    }
    closedir(dir);

    /* Einfache Sortierung der Dateinamen */
    for (size_t i = 0; i < num_files; i++)
        for (size_t j = i + 1; j < num_files; j++)
            if (strcmp(dat_files[i], dat_files[j]) > 0) {
                char *tmp = dat_files[i];
                dat_files[i] = dat_files[j];
                dat_files[j] = tmp;
            }

    /* Fortschritt laden (Resume nach Abbruch/Neustart) */
    char progress_path[MAX_PATH];
    snprintf(progress_path, sizeof progress_path, "%s/%s", output_dir, PROGRESS_FILENAME);
    char **processed_paths = NULL;
    size_t processed_count = 0, processed_cap = 0;
    FILE *pf = fopen(progress_path, "r");
    if (pf) {
        char *line = NULL;
        size_t linecap = 0;
        ssize_t n;
        while ((n = getline(&line, &linecap, pf)) > 0) {
            while (n > 0 && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = '\0';
            if (n == 0) continue;
            if (processed_count >= processed_cap) {
                processed_cap = processed_cap ? processed_cap * 2 : 64;
                char **t = realloc(processed_paths, processed_cap * sizeof(char*));
                if (!t) break;
                processed_paths = t;
            }
            processed_paths[processed_count++] = strdup(line);
        }
        free(line);
        fclose(pf);
        if (processed_count > 0)
            printf("   Fortschritt geladen: %zu Quelldatei(en) bereits verarbeitet (Resume)\n", processed_count);
    }

    unsigned long total_lines = 0;
    time_t start = time(NULL);
    time_t last_print = start;

    int skipped_binary_count = 0;
    for (size_t fi = 0; fi < num_files; fi++) {
        char path[MAX_PATH];
        snprintf(path, sizeof path, "%s/%s", source_dir, dat_files[fi]);

        /* Bereits verarbeitet? (Resume) */
        int already_done = 0;
        for (size_t i = 0; i < processed_count; i++) {
            if (strcmp(path, processed_paths[i]) == 0) {
                already_done = 1;
                break;
            }
        }
        if (already_done) {
            printf("\n   [%zu/%zu] %s (bereits verarbeitet, übersprungen)\n", fi + 1, num_files, dat_files[fi]);
            continue;
        }

        if (!is_likely_text_file(path)) {
            if (skipped_binary_count == 0)
                fprintf(stderr, "   ⚠️ .dat-Datei(en) als Binär erkannt und übersprungen (z. B. %s)\n", dat_files[fi]);
            skipped_binary_count++;
            continue;
        }
        FILE *f = fopen(path, "r");
        if (!f) {
            fprintf(stderr, "  ⚠️ %s: %s\n", dat_files[fi], strerror(errno));
            continue;
        }
        setvbuf(f, NULL, _IOFBF, READ_BUF_SIZE);
        printf("\n   [%zu/%zu] %s\n", fi + 1, num_files, dat_files[fi]);

        skip_toa5_header(f);

        char *line = NULL;
        size_t cap = 0;
        ssize_t len;
        while ((len = getline(&line, &cap, f)) > 0) {
            char *trimmed = trim_line(line);
            if (!trimmed) continue;
            int yy, ddd, HHMM;
            if (!parse_first_field_fast(trimmed, &yy, &ddd, &HHMM)) continue;
            bucket_t *b = find_or_create_bucket(yy, ddd, HHMM);
            if (!b) continue;
            bucket_append(b, trimmed);
            total_lines++;
            if (b->count >= WRITE_BUFFER_SIZE) {
                flush_bucket(b, output_dir);
            }
            time_t now = time(NULL);
            if (total_lines % 5000 == 0 && now - last_print >= 30) {
                double elapsed = (double)(now - start);
                double rate = elapsed > 0 ? (double)total_lines / elapsed : 0;
                printf("      … %lu Zeilen, %.0f Zeilen/s\n", total_lines, rate);
                last_print = now;
            }
        }
        free(line);
        fclose(f);
        flush_all_buckets(output_dir);

        /* Fortschritt speichern (Resume bei Neustart) */
        FILE *prog = fopen(progress_path, "a");
        if (prog) {
            fprintf(prog, "%s\n", path);
            fclose(prog);
        }
        if (processed_count >= processed_cap) {
            processed_cap = processed_cap ? processed_cap * 2 : 64;
            char **t = realloc(processed_paths, processed_cap * sizeof(char*));
            if (t) processed_paths = t;
        }
        if (processed_paths) {
            processed_paths[processed_count] = strdup(path);
            if (processed_paths[processed_count]) processed_count++;
        }
    }

    flush_all_buckets(output_dir);
    for (size_t i = 0; i < num_files; i++) free(dat_files[i]);
    free(dat_files);
    for (size_t i = 0; processed_paths && i < processed_count; i++) free(processed_paths[i]);
    free(processed_paths);
    free_all_buckets();

    if (skipped_binary_count > 0)
        printf("   ⚠️ Insgesamt %d .dat-Datei(en) als Binär übersprungen.\n", skipped_binary_count);

    double elapsed = (double)(time(NULL) - start);
    printf("\n   Pass 1 fertig: %lu Zeilen in %.1f Min (%.0f Zeilen/s)\n",
           total_lines, elapsed / 60.0, elapsed > 0 ? (double)total_lines / elapsed : 0);
    return total_lines;
}

/* --- Pass 2: Sortierung nach int64-Key (schneller als String-Vergleich) --- */
typedef struct { long long key; char *line; } keyline_t;

static int cmp_keyline(const void *a, const void *b) {
    long long ka = ((const keyline_t *)a)->key;
    long long kb = ((const keyline_t *)b)->key;
    return (ka > kb) - (ka < kb);
}

/* Eine Stundendatei: chunkweise lesen, nach int64-Key sortieren, in Temp-Dateien schreiben, dann mergen. */
static void sort_one_file(const char *output_dir, const char *basename) {
    char path[MAX_PATH];
    snprintf(path, sizeof path, "%s/%s", output_dir, basename);
    FILE *f = fopen(path, "r");
    if (!f) return;
    setvbuf(f, NULL, _IOFBF, READ_BUF_SIZE);

    keyline_t *chunk = malloc(SORT_CHUNK_SIZE * sizeof(keyline_t));
    if (!chunk) { fclose(f); return; }
    size_t nchunk = 0;
    char *line = NULL;
    size_t cap = 0;
    char stem[MAX_PATH];
    size_t blen = strlen(basename);
    if (blen > 4 && strcmp(basename + blen - 4, ".dat") == 0)
        snprintf(stem, sizeof stem, "%.*s", (int)(blen - 4), basename);
    else
        strncpy(stem, basename, sizeof stem - 1);
    stem[sizeof stem - 1] = '\0';
    char temp_pattern[MAX_PATH];
    snprintf(temp_pattern, sizeof temp_pattern, "%s/%s_sort_%%04d.tmp", output_dir, stem);
    char temp_path[MAX_PATH];
    int temp_index = 0;

    while (getline(&line, &cap, f) > 0) {
        char *t = trim_line(line);
        if (!t) continue;
        long long key;
        if (!parse_to_sort_key(t, &key)) key = 0;
        if (nchunk >= SORT_CHUNK_SIZE) {
            qsort(chunk, nchunk, sizeof(keyline_t), cmp_keyline);
            snprintf(temp_path, sizeof temp_path, temp_pattern, temp_index++);
            FILE *out = fopen(temp_path, "w");
            if (out) {
                setvbuf(out, NULL, _IOFBF, WRITE_BUF_SIZE);
                for (size_t i = 0; i < nchunk; i++) {
                    fputs(chunk[i].line, out);
                    if (chunk[i].line[strlen(chunk[i].line)-1] != '\n') fputc('\n', out);
                    free(chunk[i].line);
                }
                fclose(out);
            } else
                for (size_t i = 0; i < nchunk; i++) free(chunk[i].line);
            nchunk = 0;
        }
        chunk[nchunk].key = key;
        chunk[nchunk++].line = strdup(t);
    }
    free(line);
    fclose(f);

    if (nchunk > 0) {
        qsort(chunk, nchunk, sizeof(keyline_t), cmp_keyline);
        snprintf(temp_path, sizeof temp_path, temp_pattern, temp_index++);
        FILE *out = fopen(temp_path, "w");
        if (out) {
            setvbuf(out, NULL, _IOFBF, WRITE_BUF_SIZE);
            for (size_t i = 0; i < nchunk; i++) {
                fputs(chunk[i].line, out);
                if (chunk[i].line[strlen(chunk[i].line)-1] != '\n') fputc('\n', out);
                free(chunk[i].line);
            }
            fclose(out);
        } else
            for (size_t i = 0; i < nchunk; i++) free(chunk[i].line);
    }
    free(chunk);

    if (temp_index == 0) return;
    if (temp_index == 1) {
        snprintf(temp_path, sizeof temp_path, temp_pattern, 0);
        rename(temp_path, path);
        return;
    }
    /* K-Way-Merge: alle Temp-Dateien öffnen, Zeile mit kleinstem Key ausgeben. */
    FILE **temps = malloc((size_t)temp_index * sizeof(FILE*));
    char **cur_line = malloc((size_t)temp_index * sizeof(char*));
    size_t *cap_line = malloc((size_t)temp_index * sizeof(size_t));
    long long *cur_key = malloc((size_t)temp_index * sizeof(long long));
    if (!temps || !cur_line || !cap_line || !cur_key) {
        if (temps) free(temps);
        if (cur_line) free(cur_line);
        if (cap_line) free(cap_line);
        if (cur_key) free(cur_key);
        for (int i = 0; i < temp_index; i++) {
            snprintf(temp_path, sizeof temp_path, temp_pattern, i);
            remove(temp_path);
        }
        return;
    }
    for (int i = 0; i < temp_index; i++) {
        snprintf(temp_path, sizeof temp_path, temp_pattern, i);
        temps[i] = fopen(temp_path, "r");
        if (temps[i]) setvbuf(temps[i], NULL, _IOFBF, READ_BUF_SIZE);
        cur_line[i] = NULL;
        cap_line[i] = 0;
        cur_key[i] = 0;
        if (temps[i] && getline(&cur_line[i], &cap_line[i], temps[i]) > 0) {
            char *t = trim_line(cur_line[i]);
            parse_to_sort_key(t ? t : cur_line[i], &cur_key[i]);
        } else if (temps[i]) { fclose(temps[i]); temps[i] = NULL; }
    }
    FILE *out = fopen(path, "w");
    if (!out) {
        for (int i = 0; i < temp_index; i++) {
            free(cur_line[i]);
            if (temps[i]) fclose(temps[i]);
            snprintf(temp_path, sizeof temp_path, temp_pattern, i);
            remove(temp_path);
        }
        free(temps); free(cur_line); free(cap_line); free(cur_key);
        return;
    }
    setvbuf(out, NULL, _IOFBF, WRITE_BUF_SIZE);
    int active = temp_index;
    while (active > 0) {
        int best = -1;
        for (int i = 0; i < temp_index; i++) {
            if (!temps[i] || !cur_line[i]) continue;
            if (best < 0 || cur_key[i] < cur_key[best])
                best = i;
        }
        if (best < 0) break;
        fputs(cur_line[best], out);
        if (cur_line[best][strlen(cur_line[best])-1] != '\n') fputc('\n', out);
        if (getline(&cur_line[best], &cap_line[best], temps[best]) <= 0) {
            free(cur_line[best]);
            cur_line[best] = NULL;
            fclose(temps[best]);
            temps[best] = NULL;
            active--;
        } else {
            char *t = trim_line(cur_line[best]);
            parse_to_sort_key(t ? t : cur_line[best], &cur_key[best]);
        }
    }
    fclose(out);
    free(cur_key);
    for (int i = 0; i < temp_index; i++) {
        free(cur_line[i]);
        if (temps[i]) fclose(temps[i]);
        snprintf(temp_path, sizeof temp_path, temp_pattern, i);
        remove(temp_path);
    }
    free(temps);
    free(cur_line);
    free(cap_line);
}

static void pass2_sort_hourly(const char *output_dir) {
    DIR *dir = opendir(output_dir);
    if (!dir) return;
    struct dirent *ent;
    char **names = NULL;
    size_t n = 0, cap = 0;
    while ((ent = readdir(dir)) != NULL) {
        if (strncmp(ent->d_name, "gor_", 4) != 0) continue;
        size_t len = strlen(ent->d_name);
        if (len < 9 || strcmp(ent->d_name + len - 4, ".dat") != 0) continue;
        if (strstr(ent->d_name, "_sort_")) continue; /* Temp-Dateien */
        if (n >= cap) {
            cap = cap ? cap * 2 : 64;
            char **t = realloc(names, cap * sizeof(char*));
            if (!t) break;
            names = t;
        }
        names[n++] = strdup(ent->d_name);
    }
    closedir(dir);
    for (size_t i = 0; i < n; i++) {
        sort_one_file(output_dir, names[i]);
        free(names[i]);
    }
    free(names);
    printf("   Pass 2: %zu Dateien sortiert.\n", n);
}

int main(int argc, char **argv) {
    const char *source = argc > 1 ? argv[1] : SOURCE_DIR_DEFAULT;
    const char *output = argc > 2 ? argv[2] : OUTPUT_DIR_DEFAULT;

    printf("============================================================\n");
    printf("Split ts_data → stündliche Dateien (C)\n");
    printf("============================================================\n");
    printf("   Quelle:    %s\n", source);
    printf("   Ausgabe:   %s\n", output);

    struct stat st;
    if (stat(source, &st) != 0 || !S_ISDIR(st.st_mode)) {
        fprintf(stderr, "   ⚠️ Quelle existiert nicht: %s\n", source);
        return 1;
    }

    printf("\n   Pass 1: Zeilen in Stundendateien appenden …\n");
    unsigned long total = pass1_stream_append(source, output);
    if (total == 0) {
        printf("   Keine Daten geschrieben.\n");
        return 0;
    }
    printf("\n   Pass 2: Stundendateien nach Timestamp sortieren …\n");
    pass2_sort_hourly(output);
    printf("   Fertig.\n");
    return 0;
}
