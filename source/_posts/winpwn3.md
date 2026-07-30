---
title: windows seh 
date: 2026-07-29 14:07:18
categories: windows
tags: [ windows, coding, seh ]
---

## SEH基本模型

今天了解了一下windows的SEH机制, 顺带和其他语言的异常处理模型做了对比. 有趣的是我意识到我更擅长从几个基本公理来展开学习, 这篇文章就以这样的思路试试看. 我会给出windows SEH的几个基本公理, 随后用这几个公理来解释各类现象

1. `__try`定义一个受保护区域, 该区域代码及其调用的代码在触发异常时, 异常会被抛出. 可以理解为异常的生产者
2. `__leave`可以跳出当前的`__try`块
3. `__except`定义异常处理器, 可以理解为异常的消费者
4. `__finally`定义终止处理器, 控制流离开`__try`块时, 无论是正常离开, unwind, return离开都会执行. 但进程被杀等极端情况除外
5. 抛出异常后首先会逐步向外搜索能够处理异常的`__except`, 执行filter时处于搜索状态, 并不会真正unwind, 也不会执行`__finally`

6. SEH在搜索的阶段, 会根据`__except(filter)`中的filter表达式返回值做如下处理.

| 返回值 | 结果 |
| --- | --- |
| EXCEPTION_CONTINUE_SEARCH | 不处理, 继续向外搜索下一个`__except` |
| EXCEPTION_EXECUTE_HANDLER | 常规处理, 进行unwind, 进入当前`__except`处理 |
| EXCEPTION_CONTINUE_EXECUTION | filter已经处理异常, 不进行unwind, 回到异常指令重试 |

7. 当确定了某个`__except`处理异常后, 正式开始unwind, 并执行遇到的`__finally`块.

> SEH的`__except`处理是通过程序自定义的filter表达式, 而常见的异常处理模型则是通过比对错误类型是否相同来实现类似的功能.

这里用python举例. 感觉这种模型下的`except ValueError`就像是SEH下的`__except((happen_err == ValueError) ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH)`.
```python
try:
    work()
except ValueError:
    recover(0)
except TypeError:
    recover(1)
finally:
    cleanup()
```

## 实际案例

这里是微软在[结构化异常处理 （C/C++）](https://learn.microsoft.com/zh-cn/cpp/cpp/structured-exception-handling-c-cpp?view=msvc-170)给出的一个案例, 根据刚刚给出的几条公理来模拟.
1. 在`RAISE_AN_EXCEPTION`前没有疑问. 输出应该是`hello\n` `in try\n` `in try\n`
2. 在`RAISE_AN_EXCEPTION`后, 根据**公理5**, 程序逐步向外搜索`__except`, 并执行其中的filter语句, 于是输出`in filter\n`
3. `__except`返回了`EXCEPTION_EXECUTE_HANDLER`, 根据**公理6**, 执行unwind
4. 在unwind过程中, 根据**公理7**, 执行遇到的`__finally`块, 输出`in finally`
5. unwind执行到`__except`, 输出`in except`
6. 程序处理异常结束, 继续执行, 输出`in world`

```c
  puts ("hello");
  __try
    {
      puts ("in try");
      __try
        {
          puts ("in try");
          RAISE_AN_EXCEPTION ();
        }
      __finally
        {
          puts ("in finally");
        }
    }
  __except (puts ("in filter"), EXCEPTION_EXECUTE_HANDLER)
    {
      puts ("in except");
    }
  puts ("world");
```

## SEH与常见的异常处理模型对比

本文一直在将SEH与其他语言异常处理进行比对, 一直忽略一个差异是两者处理的异常本身就不同

> SEH 是 Windows 提供的异常分发与栈展开机制。它常处理访问违规、除零、非法指令、守护页等 CPU/Windows 异常，也可由`RaiseException` 产生软件异常

> 其他语言的异常通常是该语言运行时定义的异常对象和类型系统；它们也可能由运行时自动产生，例如Python 的 `ZeroDivisionError`、Java 的 `NullPointerException`。

## 安全机制

在x86时代, seh的恢复信息在栈上, 可能被攻击者利用. x64时代windows把这些信息放在了只读权限的.pdata上, 可以说基本彻底封死了seh的二进制利用.

## windows其他异常处理与seh关系

让ai整理了一个windows下异常处理流程图. 配合文字梳理一下:
1. 极度简化的异常处理链顺序是 `first-chance` -> `VEH` -> `SEH` -> `UEF` -> `second-chance` -> `VCH`, 但该链条不完全准确, 请看后文分析更详细的情况
2. `first-chance`和`second-chance`属于调试器决定的步骤, 调试器会根据策略决定是否声明处理完成当前异常以让程序恢复运行. 如调试器设置的断点`int 3`也会触发异常, 这种情况下调试器显然就会声明异常被处理完成, 不再走后续异常处理链条. 否则调试器可能不处理当前异常, 由后续异常处理机制来处理
3. `VEH`是一个在`ntdll.dll`的函数指针链表, 其影响效力为进程全局. 无论异常发生在进程的哪个位置, 异常都可能走到此处
4. `SEH`上面已经说的很详细了, 对比起`VEH`, `VCH`, `UEF`这种影响进程全局的异常处理机制来说, `SEH`的影响范围只在`__try`声明的范围内, 并且可以精确到线程, 是最精准的异常处理方式
5. `UEF`基于SEH, 但其对进程范围生效, 并且生效范围晚于所有的`SEH`.(也许可以理解为一个括在main函数之外的`__try`?)
6. `VCH`严格来说是异常恢复机制. 除了调试器之外, 无论是谁声明自己处理完成异常, 让程序恢复运行, 在恢复之前都要执行`VCH`. 影响范围为进程全局, 同样是挂在`ntdll.dll`的函数指针链表
7. 如果以上错误处理机制都决定不处理该异常, 调试器会受到`second-chance`. 此时是异常处理链条的最后一环, 如果调试器选择不处理, 程序就会被正式终止, 选择恢复则会让程序恢复运行

> 特别的, UEF在附加调试器时, 只会返回`EXCEPTION_CONTINUE_SEARCH`, 直接声明自己不对异常进行处理
```
  用户态异常发生
  （CPU fault / int3 / RaiseException）
    │
    ▼
  内核捕获并保存 CONTEXT、EXCEPTION_RECORD
    │
    ▼
  [1] 调试器 first-chance？────────────── 无调试器 ─────────────┐
    │ 有                                                        │
    ▼                                                           │
  调试器收到 EXCEPTION_DEBUG_EVENT                              │
    │                                                           │
    ├─ DBG_CONTINUE：调试器处理                                 │
    │      └─ 内核恢复线程；VEH / SEH / UEF / VCH 不运行        │
    │                                                           │
    └─ DBG_EXCEPTION_NOT_HANDLED ───────────────────────────────┘
    │
    ▼
  内核将异常交给目标进程 ntdll!KiUserExceptionDispatcher
    │
    ▼
  [2] VEH 链（按链表顺序）
    │
    ├─ 某 VEH 返回 EXCEPTION_CONTINUE_EXECUTION
    │      │
    │      ▼
    │    [5] VCH 链
    │      │
    │      ▼
    │    NtContinue → 内核恢复 CONTEXT → 继续执行
    │
    └─ 所有 VEH 均 CONTINUE_SEARCH
           │
           ▼
  [3] SEH / C++ EH：按栈帧寻找处理器
           │
           ├─ 找到可处理者
           │      ├─ 继续执行型处理（或完成展开后进入处理块）
           │      └─ 恢复路径中调用 [5] VCH，然后按新 CONTEXT 继续
           │
           └─ 所有普通 SEH / C++ handler 均不处理
                  │
                  ▼
  [4] UEF / Top-level exception filter
       UnhandledExceptionFilter
         │
         ├─ 应用通过 SetUnhandledExceptionFilter 安装的回调
         │      │
#if NOT_BEING_DEBUGGED
         │      ├─ EXCEPTION_CONTINUE_EXECUTION
         │      │      └─ [5] VCH → NtContinue → 恢复（很少应这样做）
         │      ├─ EXCEPTION_EXECUTE_HANDLER
         │      │      └─ 执行崩溃策略 / 终止；通常不再进入 VCH
#endif   │      │
         │      └─ EXCEPTION_CONTINUE_SEARCH
         │
         └─ 没有应用 UEF，或 UEF 继续搜索
                  │
                  ▼
  [6] 调试器 second-chance？────────── 无调试器 ─→ WER / 进程终止
         │ 有
         ▼
  调试器收到 second-chance EXCEPTION_DEBUG_EVENT
         │
         ├─ DBG_CONTINUE：调试器处理并恢复
         │      └─ 不会倒回去调用 VCH
         │
         └─ DBG_EXCEPTION_NOT_HANDLED
                └─ 系统终止进程
```
