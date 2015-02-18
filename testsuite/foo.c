#ifdef WIN32
#include <windows.h>
#endif
#include <stdio.h>
#include <time.h>

typedef struct {
    int key;
    char * value;
} map_t;

extern int bar(int * pnum, char * ptr);

void msleep(int msec)
{
#ifdef WIN32
    Sleep(msec);
#else
    struct timespec ts;

    ts.tv_sec = msec / 1000;
    ts.tv_nsec = (msec % 1000) * 1000000;
    (void)nanosleep(&ts, NULL);
#endif
}

void foo(char *ptr, int max)
{
    map_t map;
    int count = 0;

    map.value = ptr;
    do {
	map.key = count + 1;
	count = bar(&(map.key), map.value + 1);
	printf("count: %d\n", count);
	msleep(100);
    } while (max < 0 || count < max);
}

