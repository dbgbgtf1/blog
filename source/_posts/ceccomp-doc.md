---
title: ceccomp-doc
date: 2025-4-29
categories: beyond-ctf
tag: 开源
---
# NAME

ceccomp - the seccomp analyze tools

# SYNOPSIS

```
usage: ceccomp [subcommand] [args] [options]
    [subcommand]: asm|disasm|emu|trace|probe|version|help
```

# CONCEPT

Kernel load the seccomp with ***RAW BPF BYTES***  
which may look like this  
![raw](./ceccomp-doc/raw.png)

After ceccomp resolve the ***RAW BPF BYTES***, it can print out ***HUMAN READABLE TEXT***  
May look like this  
![trace](./ceccomp-doc/trace.png)

I will call ***HUMAN READABLE TEXT*** with ***TEXT***
, and ***RAW BPF BYTES*** with ***RAW*** later

Note that the `Line CODE JT JF K` are not necessary part of ***TEXT***, I just decided to print it  
> So be sure to understand what ***TEXT*** and ***RAW*** means

# DESCRIPTION

ceccomp is a seccomp analyze tool written in C.

Asm assemble ***TEXT*** to ***RAW***  
Disasm disassemble ***RAW*** to ***TEXT***  
Emu show what will happen(KILL?ALLOW?TRACE?) when the given syscall_nr are called  
Trace trace the given [ program or pid ], and try to analyze its seccomp rules  
Probe trace the given PROGRAM, and emulate common syscall_nr with quiet mode

# INSTALL

For archlinux users, try `yay ceccomp`
It's on the aur repo now!

For others, github install is available now  
Ceccomp is still actively update, so remember to update sometimes:)
```
git clone git@github.com:dbgbgtf1/Ceccomp.git
cd Ceccomp
make ceccomp
sudo make install
```

# USAGE

## Assemble

`ceccomp asm	[ --arch= ] [ file ] [ --fmt= ]`

Assemble the ***TEXT*** to ***RAW***

`fmt` can be set to `hexfmt`, `raw` and `hexline`, default as `hexline`  
`file` should be the ***TEXT*** file, but it is default as `stdin`

> It could be useful when you need to write your own seccomp

But make sure you write the asm in correct way  
I might write a simple guide about the asm rules  
Before that, take the disasm result as example

Example:  
> `--fmt` examples

![asm_raw](./ceccomp-doc/asm_raw.png)  
![asm_hexline](./ceccomp-doc/asm_hexline.png)  
![asm_hexfmt](./ceccomp-doc/asm_hexfmt.png)

## Disassemble

`ceccomp disasm	[ --arch= ] [ file ]`

Disassemble from ***RAW*** to ***TEXT***

> It can be useful when the program don't load seccomp at once  
> So you can use gdb to get the ***RAW*** manually, Disasm will do the rest for you

Example:  
![disasm](./ceccomp-doc/disasm.png)
> asm and then disasm!

![asm_disasm](./ceccomp-doc/asm_disasm.png)

## Emulate

`ceccomp emu	[ --arch= ] [ file ] [ --quiet ] syscall_nr [ args[0-5] ip ]`

Emulate what will happen if `syscall (nr, args ...)` were called

`args[0-5]` and `ip`(instruction pointer) are default as 0  
`--quiet` mode only show the return value of emu

> It can be useful when you don't want to read ***TEXT***

Example:  
![emu](./ceccomp-doc/emu.png)
> '--quiet' mode can be useful when you only need result

![emu_quiet](./ceccomp-doc/emu_quiet.png)

## Probe

`ceccomp probe	[ --output= ] [ --arch= ] PROGRAM [ program-args ]`

Probe can trace the program and then emulate the common syscall_nr

> It can be useful to run a quick check. Pretty useful most times

Example:  
![probe](./ceccomp-doc/probe.png)

## Trace

`ceccomp trace	[ --output= ] [ --arch= ] --pid=`
`ceccomp trace	[ --output= ] PROGRAM [ program-args ]`

Trace can trace program ***RAW*** out, and then print it out to ***TEXT***  
Trace can also trace a specified pid, and then print the filter of pid out to ***TEXT***  
(note that sudo is necessary for pid trace)

> It can be useful when you want to know what seccomp a program or a pid loads

Example:  
![trace](./ceccomp-doc/trace.png)

> Special thanks for [rocketma](https://rocketma.dev/) for zsh completion script  
> It's aswesome and has everything you need   

![trace_completion](./ceccomp-doc/trace_completion.png)

> I trace chromium seccomp with `--pid=`

![trace_chrome](./ceccomp-doc/trace_pid.png)

## Option

`arch` can be set to your cpu arch when not specified  
if this won't work for you, `--arch=` will be necessary
> This is only tested in x86_64 and aarch64, if anything goes wrong, open an issue plz  

`output` is used to avoid ceccomp output mixed with program output, and default as stderr
if `stderr` still mixed with program stderr output  
use `--output=file`, ceccomp output will be written into the file
> asm disasm emu still print to stdout  
> trace probe print to stderr as default

### output tricks

![output_trick](./ceccomp-doc/output_trick.png)
![output_trick1](./ceccomp-doc/output_trick1.png)

# SUPPORTED ARCH

- i386
- x86_64
- x32
- arm
- aarch64
- mips
- mipsel
- mipsel64
- mipsel64n32
- parisc
- parisc64
- ppc
- ppc64
- ppc64le
- s390
- s390x
- riscv64

# I Need You

Tell me what do you think!
Pull request or issue is welcome!

[Project Repo](https://github.com/dbgbgtf1/Ceccomp)
