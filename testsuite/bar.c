#include <stdlib.h>

int bar(int * pnum, char * ptr)
{
    int i = 0;
    /* for testing the balloon display */
    int *invalid = NULL;
    int **pp = &invalid;

    *pp = &i;

    i = *ptr - 'a';
    i = (i + 1) % 26;
    *ptr = 'a' + i;
    *pnum += 1;
    return *pnum;
}

