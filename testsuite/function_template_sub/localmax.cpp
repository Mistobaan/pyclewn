#include <iostream>
using namespace std;

template <class T>
T localmax(T a, T b)
{
    return a > b ? a : b;
}

void print_max()
{
    cout << "max(10, 15) = " << localmax(10, 15) << endl;
    cout << "max('k', 's') = " << localmax('k', 's') << endl;
    cout << "max(10.1, 15.2) = " << localmax(10.1, 15.2) << endl;
}
