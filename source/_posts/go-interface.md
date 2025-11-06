---
title: go的interface理解?
date: 2025-11-06 16:22:13
categories: beyond-ctf
tags: coding
---

# 特性理解

go的interface有点像cpp的抽象类里面的虚函数，但是又由于go本身的特性，导致其和cpp还是有一些区别

```go
package main

import "fmt"

type Speaker interface {
	Speak() string
}

type Dog struct {}
type Person struct {}

func (d Dog) Speak() string {
	return "汪汪！"
}

func (p Person) Speak() string {
	return "你好！"
}

func MakeSound(s Speaker) {
    fmt.Println(s.Speak())
}

func main() {
	var s0 Speaker = &Person{}
	var s1 Speaker = (*Person)(nil)
	var s2 Speaker = nil

	fmt.Println(s0 == nil)
	fmt.Println(s0.Speak())

	fmt.Println(s1 == nil)
	fmt.Println(s1.Speak())

	fmt.Println(s2 == nil)
	// fmt.Println(s2.Speak())
}
```

示例的结果类似于
```
false
你好！
false
panic: runtime error: invalid memory address or nil pointer dereference
[signal SIGSEGV: segmentation violation code=0x1 addr=0x0 pc=0x4982df]

goroutine 1 [running]:
main.main()
	/home/dbgbgtf/Main/work/test_go/main.go:33 +0xbf
exit status 2
```

可以看到`s0`和`s1`都被认为不是`nil`。但是在调用方法时，`s0`可以，`s1`却失败了
这里可以用cpp的理解来说，`s0`和`s1`都是`Person`类型的指针，但是由于s1是空指针，无法真正调用`Speaker()`

`s1`和`s2`的区别则在于类型，可以看到这里和cpp不一样。在赋值时，`*Person`的这个类型就应该被赋给`s1`了
所以在检查`s1 == nil`时，会返回一个false。因为`s1`的类型为`*Person`
而`s2`则是一个空类型空指针，所以在检查`s2 == nil`时，返回了`true`

# 实际使用?

我刚刚开始学go，还没写过什么go项目，所以只是猜测下
这个东西应该类似于cpp的抽象类，只不过他不能带上变量，而只能储存方法
可以比较好的抽象一些类似的结构体方法于一个类型
