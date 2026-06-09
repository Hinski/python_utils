#!/usr/bin/env Rscript
# Ombrothermic (Walter–Lieth) diagrams via climatol::diagwl()
# Data: ESSD final_datatables (daily), five stations (without Mole).
#
# Usage:
#   Rscript ombrothermic_climatol.R
#   Rscript ombrothermic_climatol.R --outdir plots

suppressPackageStartupMessages({
  if (!requireNamespace("climatol", quietly = TRUE)) {
    install.packages("climatol", repos = "https://cloud.r-project.org")
  }
  library(climatol)
  library(grid)
})

DATA_DIR <- "/Users/hingerl-l/Data/essd_data_tables/final_datatables"
STATIONS <- c("Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga")
MIN_DAYS_PER_MONTH <- 10L

parse_args <- function() {
  trailing <- commandArgs(trailingOnly = TRUE)
  all_args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", all_args, value = TRUE)
  script_dir <- if (length(file_arg)) {
    dirname(sub("^--file=", "", file_arg[1]))
  } else {
    getwd()
  }
  outdir <- file.path(script_dir, "plots")
  if (length(trailing) >= 2 && trailing[1] == "--outdir") {
    outdir <- trailing[2]
  }
  outdir
}

load_daily <- function(station, data_dir = DATA_DIR) {
  path <- file.path(data_dir, paste0(station, "_daily.csv"))
  if (!file.exists(path)) {
    stop("File not found: ", path)
  }
  hdr <- scan(path, what = "", nlines = 1, sep = ",", quiet = TRUE)
  d <- read.csv(
    path,
    skip = 2,
    header = FALSE,
    col.names = hdr,
    na.strings = c("-9999", "-9999.0", "NA", "NAN", "nan")
  )
  d$date <- as.Date(as.character(d$TIMESTAMP), format = "%Y%m%d")
  d <- d[!is.na(d$date), ]
  d$P <- as.numeric(d$P)
  d$TA <- as.numeric(d$TA)
  d$P[d$P < 0] <- NA
  d
}

#' Build 4×12 matrix for diagwl (cols = NULL): Prec, Max.t., Min.t., Ab.m.t.
#' From daily TA and P; only TA is available, so tmax = tmin = TA per day.
monthly_wl_matrix <- function(df) {
  df$year <- as.integer(format(df$date, "%Y"))
  df$month <- as.integer(format(df$date, "%m"))
  df$tmax <- df$TA
  df$tmin <- df$TA

  p_ok <- !is.na(df$P)
  p_sum <- aggregate(P ~ year + month, df[p_ok, , drop = FALSE], sum, na.rm = TRUE)
  p_n <- aggregate(P ~ year + month, df[p_ok, , drop = FALSE], function(x) sum(!is.na(x)))
  names(p_n)[3] <- "n"
  p_sum <- merge(p_sum, p_n)
  p_sum <- p_sum[p_sum$n >= MIN_DAYS_PER_MONTH, ]
  p_clim <- aggregate(P ~ month, p_sum, mean, na.rm = TRUE)

  t_ok <- !is.na(df$TA)
  tmax_clim <- aggregate(tmax ~ month, df[t_ok, , drop = FALSE], mean, na.rm = TRUE)
  tmin_clim <- aggregate(tmin ~ month, df[t_ok, , drop = FALSE], mean, na.rm = TRUE)
  abmin <- aggregate(tmin ~ month, df[t_ok, , drop = FALSE], min, na.rm = TRUE)

  months <- 1:12
  pick <- function(tab, col, m) {
    v <- tab[[col]][tab$month == m]
    if (length(v) == 0) NA_real_ else v[1]
  }

  mat <- rbind(
    Prec = sapply(months, function(m) pick(p_clim, "P", m)),
    `Max.t.` = sapply(months, function(m) pick(tmax_clim, "tmax", m)),
    `Min.t.` = sapply(months, function(m) pick(tmin_clim, "tmin", m)),
    `Ab.m.t.` = sapply(months, function(m) pick(abmin, "tmin", m))
  )
  colnames(mat) <- month.abb
  mat
}

network_mean_matrix <- function(mats) {
  arr <- simplify2array(mats)
  apply(arr, c(1, 2), mean, na.rm = TRUE)
}

#' Remove annual mean T and sum P (diagwl mtext, top-right margin).
hide_annual_summary <- function(mat) {
  grid.rect(
    x = unit(1, "npc"),
    y = unit(1, "npc"),
    width = unit(0.38, "npc"),
    height = unit(0.12, "npc"),
    just = c("right", "top"),
    gp = gpar(fill = "white", col = NA)
  )
}

#' Manual legend (bottom-centre, semi-transparent); symbols match diagwl fill styles.
add_wl_legend <- function(locale = c("en", "de")) {
  locale <- match.arg(locale)
  labels <- if (locale == "de") {
    c(
      "Temperatur",
      "Niederschlag",
      "Trockenperiode (P < 2T)",
      "Feuchtperiode (P \u2265 2T)"
    )
  } else {
    c(
      "Temperature",
      "Precipitation",
      "Arid period (P < 2T)",
      "Humid period (P \u2265 2T)"
    )
  }

  par(xpd = NA)
  # Bottom centre (npc)
  xr <- c(0.30, 0.70)
  yr <- c(0.02, 0.22)
  x1 <- grconvertX(xr[1], from = "npc", to = "user")
  x2 <- grconvertX(xr[2], from = "npc", to = "user")
  yb <- grconvertY(yr[1], from = "npc", to = "user")
  yt <- grconvertY(yr[2], from = "npc", to = "user")

  rect(
    x1, yb, x2, yt,
    col = rgb(1, 1, 1, 0.18),
    border = NA
  )

  dy <- (yt - yb) / 4.6
  ys <- yt - dy * (0.75 + 0:3)
  xs0 <- x1 + 0.07 * (x2 - x1)
  xs1 <- x1 + 0.30 * (x2 - x1)
  xt <- x1 + 0.36 * (x2 - x1)
  h <- dy * 0.34

  segments(xs0, ys[1], xs1, ys[1], col = "#e81800", lwd = 2.8)
  text(xt, ys[1], labels[1], adj = 0, cex = 0.82)
  segments(xs0, ys[2], xs1, ys[2], col = "#005ac8", lwd = 2.8)
  text(xt, ys[2], labels[2], adj = 0, cex = 0.82)

  draw_arid_symbol <- function(y) {
    rect(xs0, y - h, xs1, y + h, col = NA, border = "#e81800", lwd = 0.5)
    xv <- seq(xs0 + 0.06 * (xs1 - xs0), xs1 - 0.06 * (xs1 - xs0), length.out = 5)
    seg_h <- h * 0.50
    segments(
      xv, y - seg_h, xv, y + seg_h,
      col = "#e81800", lwd = 2.0, lty = 2, lend = "butt"
    )
  }

  draw_humid_symbol <- function(y) {
    rect(xs0, y - h, xs1, y + h, col = NA, border = "#005ac8", lwd = 0.5)
    xv <- seq(xs0 + 0.07 * (xs1 - xs0), xs1 - 0.07 * (xs1 - xs0), length.out = 4)
    segments(
      xv, rep(y - h, length(xv)), xv, rep(y + h, length(xv)),
      col = "#005ac8", lwd = 1.3
    )
  }

  draw_arid_symbol(ys[3])
  draw_humid_symbol(ys[4])
  text(xt, ys[3], labels[3], adj = 0, cex = 0.82)
  text(xt, ys[4], labels[4], adj = 0, cex = 0.82)
}

save_diagwl <- function(
    mat,
    path,
    width = 9,
    height = 7,
    res = 150,
    legend = TRUE,
    locale = "en"
) {
  png(path, width = width * res, height = height * res, res = res)
  on.exit(dev.off(), add = TRUE)
  diagwl(
    mat,
    cols = NULL,
    stname = "",
    alt = NA,
    per = "",
    mlab = "en",
    shem = FALSE
  )
  if (legend) {
    add_wl_legend(locale = locale)
  }
  hide_annual_summary(mat)
}

main <- function() {
  outdir <- parse_args()
  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
  station_dir <- file.path(outdir, "ombrothermic_climatol_stations")
  dir.create(station_dir, recursive = TRUE, showWarnings = FALSE)

  mats <- list()
  meta <- list()

  cat("climatol::diagwl — ESSD final_datatables (daily)\n")
  cat(strrep("=", 55), "\n", sep = "")

  for (st in STATIONS) {
    df <- load_daily(st)
    df$year <- as.integer(format(df$date, "%Y"))
    mat <- monthly_wl_matrix(df)
    mats[[st]] <- mat
    meta[[st]] <- c(
      year_start = min(df$year, na.rm = TRUE),
      year_end = max(df$year, na.rm = TRUE)
    )

    cat("\n", st, " (", meta[[st]][1], "–", meta[[st]][2], ")\n", sep = "")
    print(round(mat, 1))

    save_diagwl(mat, file.path(station_dir, paste0(st, ".png")))
  }

  mat_mean <- network_mean_matrix(mats)
  rownames(mat_mean) <- rownames(mats[[1]])
  colnames(mat_mean) <- colnames(mats[[1]])

  cat("\nMittel (alle Stationen, n=", length(STATIONS), "):\n", sep = "")
  print(round(mat_mean, 1))

  out_mean <- file.path(outdir, "ombrothermic_climatol_mean.png")
  out_copy <- file.path(outdir, "ombrothermic.png")
  save_diagwl(mat_mean, out_mean)
  file.copy(out_mean, out_copy, overwrite = TRUE)

  rows <- list()
  for (s in STATIONS) {
    m <- mats[[s]]
    for (i in seq_len(nrow(m))) {
      for (j in seq_len(ncol(m))) {
        rows[[length(rows) + 1]] <- data.frame(
          station = s,
          variable = rownames(m)[i],
          month = colnames(m)[j],
          value = m[i, j],
          stringsAsFactors = FALSE
        )
      }
    }
  }
  for (i in seq_len(nrow(mat_mean))) {
    for (j in seq_len(ncol(mat_mean))) {
      rows[[length(rows) + 1]] <- data.frame(
        station = "Network_mean",
        variable = rownames(mat_mean)[i],
        month = colnames(mat_mean)[j],
        value = mat_mean[i, j],
        stringsAsFactors = FALSE
      )
    }
  }
  write.csv(
    do.call(rbind, rows),
    file.path(outdir, "ombrothermic_climatol_climatology.csv"),
    row.names = FALSE
  )

  cat("\n✓ ", out_mean, "\n", sep = "")
  cat("✓ ", out_copy, "\n", sep = "")
  cat("✓ ", station_dir, "/\n", sep = "")
}

if (sys.nframe() == 0L) {
  main()
}
