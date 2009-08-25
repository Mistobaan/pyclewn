int bar(int * pnum, char * ptr)
{
    int i;

    i = *ptr - 'a';
    i = (i + 1) % 26;
    *ptr = 'a' + i;
    *pnum += 1;
    return *pnum;
}

