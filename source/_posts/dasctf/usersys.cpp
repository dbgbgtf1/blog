#include <cstddef>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>

// clang-format off
#define SIGSEGVERR do { cout << "SIGSEGV Invalid Instruction!" << endl; exit(1); } while (0);
#define FILEERR do { cout << "File Operation Error" << endl; exit(1); } while (0);
// clang-format on

using namespace std;

class User;
class Guest;
class Admin;
class Root;

static Guest *guest;
static Root  *root;
static Admin *admin;

static void init(void)
{
    setbuf(stdin, NULL);
    setbuf(stdout, NULL);
    setbuf(stderr, NULL);
    puts("\x1b[94m");
    puts("   __  _______ __________     _______  _____________________  ___");
    puts("  / / / / ___// ____/ __ \\   / ___/\\ \\/ / ___/_  __/ ____/  |/  ""/");
    puts(" / / / /\\__ \\/ __/ / /_/ /   \\__ \\  \\  /\\__ \\ / / / __/ / /|_/ ""/ ");
    puts("/ /_/ /___/ / /___/ _, _/   ___/ /  / /___/ // / / /___/ /  / /  ");
    puts("\\____//____/_____/_/ |_|   /____/  /_//____//_/ /_____/_/  /_/   ");
    puts("\x1b[0m");
}
class User
{
public:
    char name[8] = "User";
    long uid;

    User(int uid_)
        : uid(uid_)
    {
    }
    virtual void operation(void) { cout << "here are the basic class" << endl; }
};

class Root : public User
{
public:
    Root(void)
        : User(0)
    {
        strcpy(name, "Root");
    }

    void operation(void) override
    {
        cout << "haha of course the system have root user" << endl;
        system("/bin/sh");
    }
};

const char FILE_NAME[] = "Guest_Data";

class Guest : public User
{
public:
    char      guest_book[5][8];
    short int login_count;

    void StoreGuestData()
    {
        ofstream file(FILE_NAME);

        if (file.is_open())
        {
            file << login_count << endl;
            for (int i = 0; i < 5; i++)
            {
                file << guest_book[i] << endl;
            }
            file.close();
        }
        else
            FILEERR;
    }

    void GetGuestData()
    {
        ifstream file(FILE_NAME);

        if (file.is_open())
        {
            file >> login_count;
            for (int i = 0; i < 5; i++)
            {
                file >> guest_book[i];
            }
            file.close();
        }
        else
            FILEERR;
    }

    Guest(void)
        : User(2000)
    {
        strcpy(name, "Guest\x00");
    }

    void ClearGuestData()
    {
        for (int i = 0; i < 5; i++)
        {
            for (int j = 0; j < 8; j++)
            {
                guest_book[i][j] = '\0';
            }
        }
        login_count = 0;
        StoreGuestData();
    }

    void ShowGuestName()
    {
        for (int i = 0; i < login_count; i++)
        {
            cout << guest_book[i] << endl;
        }
    }

    void operation() override
    {
        GetGuestData();

        if (login_count < 5)
        {
            cout << "login as guest" << endl;
            cout << "wanna leave your name?[y/n]" << endl;
            string oper;
            cin >> oper;

            if (oper.find("y") == 0)
            {
                GetGuestData();
                cout << ">>>";
                read(0, &guest_book[login_count], 8);
                cout << "success" << endl << "logout now" << endl;
                login_count++;
                StoreGuestData();
                return;
            }

            else if (oper.find("n") == 0)
            {
                cout << "byebye" << endl;
                return;
            }

            else
                SIGSEGVERR;
        }

        else
            cout << "no more room for anthoer guest,try it later" << endl;
    }
};

class Admin : public User
{
public:
    Admin(void)
        : User(1000)
    {
        strcpy(name, "Admin");
    }

    void operation(void) override
    {
        string oper;
        cout << "login as admin " << endl;
        while (true)
        {
            cout << "show all guest names/clear guest "
                    "book/logout[show/clear/logout]"
                 << endl
                 << ">>>";
            cin >> oper;
            if (oper.find("clear") == 0)
                guest->ClearGuestData();
            else if (oper.find("show") == 0)
            {
                guest->GetGuestData();
                guest->ShowGuestName();
                cout << "success" << endl;
            }
            else if (oper.find("logout") == 0)
                return;
            else
                SIGSEGVERR;
        }
    }
};

int main(void)
{
    init();
    guest = new Guest;
    root  = new Root;
    admin = new Admin;
    string login_account;

    while (true)
    {
        cout << "hello! who are u[root/admin/guest]" << endl;
        cin >> login_account;

        if (login_account.find("root") == 0)
            cout << "no,the system don't have root user" << endl;
        else if (login_account.find("admin") == 0)
            admin->operation();
        else if (login_account.find("guest") == 0)
            guest->operation();
        else
            SIGSEGVERR;
    }
}
