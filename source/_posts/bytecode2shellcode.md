---
title: v8: one way from bytecode to shellcode
date: 2026-04-30 16:46:36
categories: chrome/v8研究
tags: [ v8, bytecode ]
---

## 背景介绍

今天闲得没事干在github搜v8 exploit, 搜到[cve-2025-10891](https://github.com/Wa1nut4/v8-exploit/tree/main/CVE-2025-10891). 给了一篇利用手法的[文章](https://osec.io/blog/2026-04-01-patch-gap-to-mobile-renderer-rce/), 仔细一看挺有意思的. 并不单纯因为漏洞本身, 而是看到的利用手法可能比较有代表性.

前两天是总结了另一种类型, 从TDZ入手的HoleAttack. 今天这种是从igntion bytecode错位执行入手.

## 利用手法介绍

这种利用手法假设通过某个漏洞已经可以获取错位bytecode跳转. 而且版本不能太新, 因为用到的runtime函数(%SerializeModule, %DeserializeModule)在[2025-08](https://chromium-review.googlesource.com/c/v8/v8/+/6875821)被移到了`d8.wasm`下, 真实浏览器环境可能用不了了. 以及在新版`d8.wasm.DeserializeModule`有对raw machine code的hash校验, 不允许对其修改. hash校验存在bss上, 我看过了:(

首先从错位构造入手, 因为用`a = 0x12345678`这样的js语句可以生成4个字节可控(实际上并不能用到0xffffffff, 由于Smi的限制)的bytecode`01 0d 78 56 34 12 LdaSmi.ExtraWide [305419896]`, 除去两个字节用来跳转, 我们就可以有两个字节用来做别的事.

如果两个字节不够, 还可以通过`a + 0x12345678`来构造总计八个字节可控的bytecode`01 4c 78 56 34 12 00 00 00 00 AddSmi.ExtraWide [305419896], [0]`. 其中前四个字节是我们的立即数, 同样受到Smi的限制. 而后四个字节是feedback slot index, 这只能通过不停的创建新的js语句来增长.
类似于
```js
let a = 0;
function make(target_slot)
{
    return "a+1;\n".repeat(target_slot);
}
```
很扯淡对吧. 这样就让整个八个字节的构造相当麻烦和低效. 不过好在似乎只需要构造两次, 因为只有调用Runtime函数才需要比较长的bytecode执行, 其他很多操作都能在两个字节内完成.

## 可能可用的cve

cve-2025-10891存在理论可能, 因为它可以达成bytecode跳转. cve-2025-9132也存在理论可能, 之前我用这个cve能打出bytecode跳转.

## 修复方案以及可用范围

(下次有空再研究..先记录下
