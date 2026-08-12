---
title: ceccomp-blog-3 ebpf功能更新
date: 2026-08-11 16:31:04
categories: ceccomp-dev-blog
tags: [ ceccomp, c, ebpf ]
---

> 最近为ceccomp创建了组织, 并且将原仓库迁移到了该组织🎉. https://github.com/ceccomp/ceccomp

# 前言

最近在完善ceccomp准备推出的新功能 capture. capture分为两种模式, `global`和`pid`, 两种模式的原理都是在内核加载ebpf程序, 从而更加轻松的获取到用户态无法获取的信息, 更加灵活自由的获取到filter信息.

> 本文的pid实际上指thread id. 这是ceccomp命名上的历史遗留问题, 最开始命名trace的pid模式我们没有关注pid/tid区分, 但后来注意到`trace pid`包括`capture pid`的精度实际上一直是在tid. 所以我们决定就统一叫做pid好了, 如kthread这种习惯叫法我们则保留

# ebpf介绍

事先声明一下本文对于ebpf描述未必准确, 大多是个人当前浅薄理解. 只是介绍capture功能前简单科普一下, 顺便供自己参考和回顾, 后续有新的理解也可能会继续更新.

## ebpf基本性质

- ebpf可以挂在内核的许多位置. 如某个内核函数的入口/出口处. 所以ebpf的挂载和触发是内核全局的. 而bpf只会在加载了该bpf的进程触发syscall的入口处被调用, 其影响范围仅限于加载了该bpf的进程本体

- ebpf仍然是一种低级, 接近于汇编的虚拟机语言, 但许多语言都有工具对其提供封装. 例如想用c写ebpf可以使用libbpf, 使得我们并不需要真正去写裸的ebpf指令. 而bpf由于使用范围比较局限, 几乎没有工具对其提供封装. 我所知的只有ceccomp和seccomp-tools.

## ebpf限制

由于ebpf直接挂在内核上运行, 内核对其有非常严格的安全或性能检查.

- 申请`ringbuf`之后强制要求所有分支都要`submit`或`discard`. 以防在内核中造成内存泄漏甚至是安全隐患.

- ebpf中还不允许存在无限循环的可能性, 因为ebpf代码可能被整个系统上不同进程调用内核时不停的调用, 内核认为无限循环的ebpf代码会影响机器工作效率, 甚至导致内核出现死循环.

- ebpf中读取结构体的方式也比较复杂, 不仅要像内核那样区分用户态/内核态读写内存, 还要使用一系列`bpf_core_read`api来以内核允许的方式安全读取结构体成员. 下面是一些例子
```c
BPF_CORE_READ_INTO (&filter, task, seccomp.filter);
// 实际作用是 filter = task->seccomp.filter
```
`bpf_core_read`系列api实际上有两个作用, 1是防止ebpf代码越界对内核内存进行读写, 2是方便libbpf对其进行core处理. 如你所见该api会获取你想要的成员名, 在libbpf加载这些代码时会根据内核BTF(BTF我简单将其理解为调试信息类似物, 用来根据指定成员名获取到该成员在结构体内部的偏移)将当前内核的正确偏移写入ebpf待重定位的代码

总是看到有人拿javascript之于浏览器类比ebpf之于内核, 个人认为还挺恰当的. 相同之处在于设定好极高的安全限制, 再允许外部代码在高权限环境下运行, 不同的是js更加好写, 而ebpf更加高效. *安全-高效-好写* 这何尝不是编程语言的不可能三角呢?

## ebpf加载过程(libbpf为例)

1. `clang -target bpf`编译.bpf.c代码, 生成.bpf.o文件
2. libbpf提供`app_bpf__open_and_load`函数, 加载ebpf时会申请内核map. 例如.bss、.data、.rodata被创建为不同的内核map, libbpf在这之后会将mapfd写入待重定位的段引用
3. libbpf会根据`/sys/kernel/btf/vmlinux`提供的内核结构体偏移信息做CORE(compile once, run everywhere), .bpf.o会记录读取的结构体成员, 之后libbpf会写入待重定位的结构体访问偏移
4. 提交代码段, libbpf将翻译后的ebpf代码通过bpf系统调用提交, 内核对其进行验证并加载或拒绝

这部分描述的比较简单, 实际情况比这复杂多了, 但作为初步学习和使用ebpf的人, 了解到这一步也够用了

## ringbuf

目前ebpf主要和用户态进行通信的方式是ringbuf. 可以理解为用户态程序和内核的ebpf有一块共享内存. ebpf可以申请ringbuf, 在写入数据后将其提交. 用户态程序使用`ring_buffer__poll`可以收到提交事件, 并且用指定的回调函数来处理该事件.

下面是一些伪代码助于理解.
```c
// ebpf
map ringbuf = RINGBUF(256KB)

on_tracepoint(...) {
  event = ringbuf.reserve(sizeof(Event))
  if (!event)
      return

  event.pid = current_pid()
  event.data = "hello from ebpf"

  ringbuf.submit(event)
}

// 用户态
load_and_attach_ebpf_program()

ringbuf = open_ringbuf_map("ringbuf")

while (true) {
  ringbuf.poll(event => {
      print(event.pid, event.data)
  })
}
```

# capture功能

## global模式

这个模式将一个ebpf程序挂载在内核加载seccomp的入口点(`seccomp_check_filter`)和出口点(`do_seccomp`), 在当前机器上进行全局(`global`)的监测seccomp加载.

程序会在入口点获取到用户态传入的filter(准确来说这时候已经是被复制到内核态的filter了), 但是这时无法判断该filter是否被内核成功加载, 所以先按照当前进程的pid存入ebpf下的hash_map. 而在出口点根据pid索引拿到同样的filter, 并且根据`do_seccomp`的返回值来确认filter是否加载成功. 如果加载成功, 就将其通过ringbuf发送到用户态

## pid模式

### 设计思路

设计全局模式的时候, 我们发现从内核进程task结构体可以获取到`seccomp_filter`这个结构体, 而`seccomp_filter`是一个链表节点, 本身指向`struct bpf_prog *prog`, prev指向`seccomp_filter *prev`, 在`struct bpf_prog *prog`中可以获取到该进程每次加载的`bpf filter`. 于是我们就有了个想法, 是不是只要获取了某个进程的task结构体, 就可以dump出该进程历史加载的所有`bpf filter`, pid模式应运而生

> 后来我们发现结构体会将cbpf转换ebpf进行保存(取决于内核配置和版本, 但现代内核通常统一将cbpf转换为ebpf进行保存和执行), 这促使着我们开发了对ebpf的disasm功能
```
struct seccomp_filter {
	refcount_t refs;
	refcount_t users;
	bool log;
	bool wait_killable_recv;
	struct action_cache cache;
	struct seccomp_filter *prev;
	struct bpf_prog *prog;
	struct notification *notif;
	struct mutex notify_lock;
	wait_queue_head_t wqh;
};

struct bpf_prog {
	u16 pages;
	u16 jited: 1;
	u16 jit_requested: 1;
	u16 gpl_compatible: 1;
	u16 cb_access: 1;
	u16 dst_needed: 1;
	u16 blinding_requested: 1;
	u16 blinded: 1;
	u16 is_func: 1;
	u16 kprobe_override: 1;
	u16 has_callchain_buf: 1;
	u16 enforce_expected_attach_type: 1;
	u16 call_get_stack: 1;
	u16 call_get_func_ip: 1;
	u16 call_session_cookie: 1;
	u16 tstamp_type_access: 1;
	u16 sleepable: 1;
	enum bpf_prog_type type;
	enum bpf_attach_type expected_attach_type;
	u32 len;
	u32 jited_len;
	union {
		u8 digest[32];
		u8 tag[8];
	};
	struct bpf_prog_stats *stats;
	u8 *active;
	unsigned int (*bpf_func)(const void *, const struct bpf_insn *);
	struct bpf_prog_aux *aux;
	struct sock_fprog_kern *orig_prog;
	union {
		struct {
			struct {} __empty_insns;
			struct sock_filter insns[0];
		};
		struct {
			struct {} __empty_insnsi;
			struct bpf_insn insnsi[0];
		};
	};
};
```

接下来我们查询到了`bpf_task_from_pid`这个api, 可以获取到指定pid的task结构体, 那么整条线就串起来了. 读取结构体的思路如下, 理论上这样可以dump到任意进程的所有加载过的filter结构体(但是ebpf不允许任何理论上可能无限循环, 所以这里只能加上一个32的人为截断)
```c
struct task_struct *task = bpf_task_from_pid (target_pid);
struct seccomp_filter *filter; BPF_CORE_READ_INTO (&filter, task, seccomp.filter);
for (uint32_t prog_idx = 0; filter != NULL && prog_idx < 32; prog_idx++)
{
    struct seccomp_filter *next;
    struct bpf_prog *prog;
    BPF_CORE_READ_INTO (&prog, filter, prog);

    dump_prog (prog);

    BPF_CORE_READ_INTO (&next, filter, prev);
    filter = next;
}
```

### pid模式的一些缺憾

`bpf_task_from_pid`这个api虽然好用, 但直到6.2才被引入(我和另一位主要开发者[🚀](https://rocketma.dev/)都是使用archlinux, 但我们肯定也希望该功能能被更多人使用). 除开版本之外, `bpf_task_from_pid`该api的pid必须是在initns中的pid, 也就是在容器等环境中可能会出现非预期的工作表现.

`bpf_task_from_vpid`的pid则是current_ns中的, 但该api就得到6.13版本了, 所以我们暂时放弃使用该api
