---
title: sshd内存码实现后门登陆
date: 2025-07-17
categories: beyond-ctf
tags: 开源
---

# 前言

前段时间期末考，一直在协会和int复习，然后不知道咋的聊到了在sshd里面注入内存码
我说这个用ptrace挺好做的，你要是感兴趣我先写个demo给你看。

# 实现思路和优化过程

## 最初步的思路

最开始看代码的时候发现一个难处理的点，sshd虽然本身是一个很适合注入的常驻进程
但是他并不负责处理登陆请求，或者说他只负责accept，然后就将fd什么的交给sshd-session进程

但是因为看到accept系统调用的第二个参数会返回对方的ip地址和对方的port信息
我想到可以用这个来区分是否需要开启后门
这样就可以简单的做到在sshd的进程上根据accept的ip地址和port信息来判断是否开启一个简单的bash后门

但是我不想止步于此，我想让后门是一个真正的ssh连接，后文会描述我如何继续

## 真正的ssh连接

sshd-session进程是sshd的子进程
刚开始我和🚀都以为他只是单单fork了一下，然后就跳到某个函数开始执行sshd-session的逻辑
所以我们最开始想的是用ptrace劫持sshd的got表来注入钩子

但是事实证明我们想的太简单了，也太小瞧sshd了。
sshd在fork之后使用了execv，相当于在这之前的所有内存码驻留全部失效，被替换为sshd-session文件内容
sshd-session是一个单独的可执行文件，这样可以实现sshd-session的热重启
而且还能让我这样想劫持got的思路失效

然后我就想到可以将ptrace的逻辑注入sshd进程，在后门逻辑开启时，fork自己，
然后让一个进程trace另一个execv sshd-session的进程，
这样就可以做到运行时更改sshd-session的内容了，从而理论可以实现后门公私钥

然后我对于sshd进程的操作就是这样的，劫持accept和execv的got表
在accept里面根据端口号判断是否开启后门，在execv里fork，然后由一个进程trace另一个execv的进程
并且可以针对内存进行修改，从而实现后门

## 大量编写汇编代码的优化

作为一个二进制手，手写点汇编代码不是太难的事，但是当工作量太大时，手写汇编代码明显不合理
我想到的解决办法是先写c代码，由gcc编译成.o后，再由objcopy提取出单纯的text段(text段就纯粹是汇编了)
然后再由python脚本读取text段，将其以`char sshd_accept[] = "\x48\x63 ... "`的形式放在一个头文件中

在主程序编译时include这个头文件，主程序只负责将头文件中的char数组注入sshd进程

这样明显比手写来的更容易，最重要的是能节约时间，就不需要把时间花在检查汇编代码上了

## 奇怪的逻辑

当我把上述工作完成后，接下来我想要了解sshd-session如何检查公私钥，如何判断是否通过
举个例子，用公私钥的ssh连接是这样的`ssh -i private_key root@ip`
在服务器的~/.ssh/authorized_keys里面如果有这个private_key所对应的公钥，就可以成功登陆

所以很自然的我想到，在sshd-session中必然存在`open ("~/.ssh/authorized_keys")`和read authorized_keys的逻辑
我用gdb跟了之后发现确实有这样的逻辑，出现在mm_answer_keyallowed函数后

但是很奇怪的是sshd-session会执行一次open和read，而后还会再执行一次同样的逻辑
甚至就是再执行一次mm_answer_keyallowed的上层函数(具体从哪开始我没跟)

问了下gpt后，了解到sshd-session中还有存在更进一步的降权操作
假设以非root用户登录，则sshd-session在执行一次mm_answer_keyallowed检查后，如果通过
还会让非root用户的进程sshd-auth再执行一次，第二次再通过才会认为认证成功

但是当以root用户登陆时，就没有再次降权的必要了，所以两次认证都在sshd-session进程中完成
可能这么设计是为了让一些比较苛刻条件下的漏洞利用失效

但是对于我这样从sshd进程trace到sshd-session进程的利用来说倒不是大问题

# 最后

还有值得提的就是accept通过端口来判断是否开启后门并不是一个特别完美的方案
因为大多时候你和服务器并不是直连，你使用的端口未必是你的网络转发你的连接时对外使用的端口
所以除非你使用一台公网服务器，或者一些歪门邪道让你能强制使用特定端口与服务器进行通信
否则这个accept都是用不了的

[repo](https://github.com/dbgbgtf1/sshd_injector)
