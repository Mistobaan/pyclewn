void test(void) {}
void test(int a)
{
    a = a + 1;
}
void test(int a, int b) {}

int main()
{
    test();
    test(0);
    test(0, 0);
}
