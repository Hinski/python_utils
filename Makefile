# Standard-Ziel: C-Programm split_ts_data_to_hourly bauen
# Nutzung: make   oder  make split_ts_data_to_hourly

CC = cc
CFLAGS = -O2 -Wall -Wextra

split_ts_data_to_hourly: split_ts_data_to_hourly.c
	$(CC) $(CFLAGS) -o split_ts_data_to_hourly split_ts_data_to_hourly.c

clean:
	rm -f split_ts_data_to_hourly

.PHONY: clean
