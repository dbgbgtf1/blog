---
title: ceccomp
date: 2025-05-07 21:37:00
categories: beyond-ctf
tags: 开源
---

# 前言

前段时间特别的无聊，想找点事情做，然后🚀向我推荐写个C语言版本的`seccomp-tools`
其实早就他有说过想干类似的事了，但是他忙很多别的事

然后由于我的机子上的`seccomp-tools`出现了奇怪的问题
![odd_problem](./ceccomp/odd_problem.png)

我又不想学太过古老的`ruby`(现在真有人用这玩意吗)
那就来吧，自己写一个C版本的`seccomp-tools`

# 命名

我将之命名为`ceccomp`，也就是将`seccomp`的`s`改为`c`，毕竟是`c`写的

# 实现功能

其实这方面应该看文档([here](https://dbgtf.org/ceccomp-doc/))
和`seccomp-tools`没啥差别，`seccomp-tools`有的基本也都有了
```
asm
disasm
dump
emu
```
我还是比较满意的，而且效果看起来也不错，在文档里也有效果演示

# 收获？

大概是第一次写十个文件的`C`项目，以前真的没写过更复杂的，😂
这次之后对`C`更有感觉了，一点点组织代码实现功能的感觉真得很棒！

大致学了一下`makefile`写法，除了`$^ $@ $<`实在有点奇怪

# 最后

快去试试吧！如果有问题欢迎提`issue`或是`pr`！

[文档地址](https://dbgtf.org/ceccomp-doc/)
[项目地址](https://github.com/dbgbgtf1/Ceccomp/tree/main)

