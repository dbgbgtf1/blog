#define _GNU_SOURCE
#include <errno.h>
#include <seccomp.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>
#include <fcntl.h>

void sandbox()
{
    scmp_filter_ctx ctx;
    ctx = seccomp_init(SCMP_ACT_KILL);

    if (ctx == NULL)
    {
        perror("seccomp_init");
        exit(EXIT_FAILURE);
    }

    if (seccomp_load(ctx) < 0)
    {
        perror("seccomp_load");
        seccomp_release(ctx);
        exit(EXIT_FAILURE);
    }

    seccomp_release(ctx);
}

void init()
{
    setbuf(stdin, NULL);
    setbuf(stdout, NULL);
    setbuf(stderr, NULL);
}

void (*vuln())(void *)
{
    void* shellcode;
    shellcode = mmap((long *)0x20240000, 0x1000, 7, 34, -1, 0);
    read(0, shellcode, 0x6);
    return shellcode;
}

char flag[0x100];
void *WriteFlag()
{
    int   fd   = open("flag", 0);
    read(fd, flag, 0x100);
    close(fd);
    return flag;
}

int main()
{
    init();

    __asm__(
	"call   WriteFlag;"
	"push   rax;"
	"call   vuln;"
	"push   rax;"
    "mov	edi, 5;"
	"call	alarm@PLT;"
	"call   sandbox;"
    "xor    rbx, rbx;"
    "xor    rcx, rcx;"
    "xor    rdx, rdx;"
    "xor    rsi, rsi;"
    "xor    r8, r8;"
    "xor    r9, r9;"
    "xor    r10, r10;"
    "xor    r11, r11;"
    "xor    r12, r12;"
    "xor    r13, r13;"
    "xor    r14, r14;"
    "xor    r15, r15;"
    "xor    rbp, rbp;"
	"pop    rax;"
	"pop    rdi;"
	"call   rax;"
);

    exit(0);
}
