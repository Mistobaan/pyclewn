class A {
    public:
	void test(void) {}
	void test(int a) {}
	void test(int a, int b) {}
};

void test(void) {}
void test(int a) {}
void test(int a, int b) {}

int main()
{
    A obj;

    obj.test();
    obj.test(0);
    obj.test(0, 0);

    test();
    test(0);
    test(0, 0);
}
