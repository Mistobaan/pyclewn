#include <vector>

int main()
{
    std::vector< std::vector<int> > v;
    std::vector<int> nested;

    nested.push_back(2);
    nested.push_back(3);
    nested.insert(nested.begin(), 1);

    v.push_back(nested);
    v.push_back(nested);

    nested.erase(nested.begin());
    nested.erase(nested.begin());
    nested.erase(nested.begin());

    return 0;
}

