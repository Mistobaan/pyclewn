#include <stdlib.h>
#include <string.h>

#define HEADER "'a' letter in "

extern void foo(char *ptr, int max, int sleep);

int main(int argc, char *argv[])
{
    int len = strlen(HEADER);
    char str[len + strlen(argv[0]) + 1];
    int max = -1; /* loop forever */
    int sleep = 100;

    strcpy(str, HEADER);
    strcpy(str + len, argv[0]);
    if (argc > 1)
        max = strtol(argv[1], (char **)0, 0);
    if (argc > 2)
        sleep = strtol(argv[2], (char **)0, 0);

    /* one full screen of blank lines */







































    foo(str, max, sleep);
    return 0;
}

