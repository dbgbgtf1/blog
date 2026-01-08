---
title: ceccomp-blog-2
date: 2026-01-08 13:31:02
categories: ceccomp-dev-blog
tags: coding
---

这个学期花了大把时间在重构ceccomp，用到了crafting interpreter中学到的编译器知识，设计了ceccomp自己的ir(Intermediate Representation)。这篇文章就当是ceccomp的开发blog兼自己的心得了

原先的ceccomp代码耦合性过高，比如emu.c的代码既处理模拟的逻辑，又要处理打印的逻辑，同时还要检查用户输入代码。这就导致代码可维护性很差，代码复用也很乱糟糟的。简单来说缺乏系统性的架构

现在经过学习crafting interpreter，了解了编译器的工作阶段。大致分为4个步骤`scan->parse->resolve->asm`
书中有一个比喻很恰当，编译器的工作就像是爬山再下山。爬山的阶段代表对用户代码理解水平的逐步提高，而下山的阶段代码将用户代码从丰富的文本信息一步步变成最简单的纯数字信息。

### scan
scan的作用是逐字节扫描原文本，由于没有形成对用户代码更高层面的理解，这里只能做一些在单字节层面的简单处理，例如跳过空格和注释。
scan最后的结果就是将逐字节的文本变成一个个的token。例如下面这段代码，就是目前ceccomp的所有token。这也就意味着在scan结束后，我们对用户的代码理解就从单字节的文本信息提高到了一个个的token
```c
typedef enum
{
  ARCH_X86, ARCH_I686, ARCH_X86_64,
  ARCH_X32, ARCH_ARM, ARCH_AARCH64,
  ARCH_LOONGARCH64, ARCH_M68K, ARCH_MIPSEL64N32,
  ARCH_MIPSEL64, ARCH_MIPSEL, ARCH_MIPS64N32,
  ARCH_MIPS64, ARCH_MIPS, ARCH_PARISC64,
  ARCH_PARISC, ARCH_PPC64LE, ARCH_PPC64,
  ARCH_PPC, ARCH_S390X, ARCH_S390,
  ARCH_RISCV64,

  KILL_PROC, KILL, ALLOW, NOTIFY,
  LOG, TRACE, TRAP, ERRNO,

  A, X, MEM, ATTR_LEN,
  ATTR_SYSCALL, ATTR_ARCH, ATTR_LOWPC, ATTR_HIGHPC,
  ATTR_LOWARG, ATTR_HIGHARG,

  RETURN, IF, GOTO, COMMA, ELSE,

  DOT,

  LEFT_BRACKET, RIGHT_BRACKET,
  LEFT_PAREN, RIGHT_PAREN,
  ADD_TO, SUB_TO, MULTI_TO,
  DIVIDE_TO, LSH_TO, RSH_TO,
  AND_TO, OR_TO, XOR_TO,

  EQUAL_EQUAL, BANG_EQUAL,
  GREATER_EQUAL, GREATER_THAN,
  LESS_EQUAL, LESS_THAN,
  AND, EQUAL,
  NEGATIVE, BANG,

  UNKNOWN, COMMENT, EOL, TOKEN_EOF,
  IDENTIFIER, LABEL_DECL, NUMBER,
  // IDENTIFIER includes SYSCALL, LABEL
  // LABEL_DECL = (IDENTIFIER + ':')
} token_type;
```
```c
char *token_pairs[] = {
  [ARCH_X86] = "i386", [ARCH_I686] = "i686", [ARCH_X86_64] = "x86_64",
  [ARCH_X32] = "x32", [ARCH_ARM] = "arm", [ARCH_AARCH64] = "aarch64",
  [ARCH_LOONGARCH64] = "loongarch64", [ARCH_M68K] = "m68k", [ARCH_MIPSEL64N32] = "mipsel64n32",
  [ARCH_MIPSEL64] = "mipsel64", [ARCH_MIPSEL] = "mipsel", [ARCH_MIPS64N32] = "mips64n32", 
  [ARCH_MIPS64] = "mips64", [ARCH_MIPS] = "mips", [ARCH_PARISC64] = "parisc64",
  [ARCH_PARISC] = "parisc", [ARCH_PPC64LE] = "ppc64le", [ARCH_PPC64] = "ppc64",
  [ARCH_PPC] = "ppc64", [ARCH_S390X] = "s390x", [ARCH_S390] = "s390",
  [ARCH_RISCV64] = "riscv64",

  [KILL_PROC] = "KILL_PROCESS", [KILL] = "KILL", [ALLOW] = "ALLOW", [NOTIFY] = "NOTIFY",
  [LOG] = "LOG", [TRACE] = "TRACE", [TRAP] = "TRAP", [ERRNO] = "ERRNO",

  [A] = "$A", [X] = "$X", [MEM] = "$mem", [ATTR_LEN] = "$scmp_data_len",
  [ATTR_SYSCALL] = "$syscall_nr", [ATTR_ARCH] = "$arch", [ATTR_LOWPC] = "$low_pc",
  [ATTR_HIGHPC] = "$high_pc", [ATTR_LOWARG] = "$low_args", [ATTR_HIGHARG] = "$high_args",

  [RETURN] = "return", [IF] = "if", [GOTO] = "goto", [COMMA] = ",", [ELSE] = "else",

  [DOT] = ".",

  [LEFT_BRACKET] = "[", [RIGHT_BRACKET] = "]",
  [LEFT_PAREN] = "(", [RIGHT_PAREN] = ")",
  [ADD_TO] = "+=", [SUB_TO] = "-=", [MULTI_TO] = "*=",
  [DIVIDE_TO] = "/=", [LSH_TO] = "<<=", [RSH_TO] = ">>=",
  [AND_TO] = "&=", [OR_TO] = "|=", [XOR_TO] = "^=",

  [EQUAL_EQUAL] = "==", [BANG_EQUAL] = "!=",
  [GREATER_EQUAL] = ">=", [GREATER_THAN] = ">",
  [LESS_EQUAL] = "<=", [LESS_THAN] = "<",
  [AND] = "&", [EQUAL] = "=",
  [NEGATIVE] = "-", [BANG] = "!",

  [UNKNOWN] = "unknown", [COMMENT] = "#", [EOL] = "line_end",
  [IDENTIFIER] = "identifier", [LABEL_DECL] = "label_decl", [NUMBER] = "number",
  // label_decl ::= IDENTIFIER + ":"
};
```
> 请留心下上面的`token_type`类型和`token_pairs`数组，后面要考(bushi

### parse
parse的作用是将scan的token根据语法组成我们的ir。这个ir在ceccomp中叫`statement_t`，代表一行的代码。
由于seccomp语法特殊性，不存在传统意义的AST语法树。我们可以用固定大小的数据结构来表达一行代码，不存在无限增长的复杂表达式(例如`uint32_t a = &*&*&*&*&*&*&*&*&*some_var;`)，也就不需要引入AST语法树的概念
在parse阶段后，我们对用户的代码的理解就从一个个的独立token升级到了完整的表达式，在ceccomp中，就是一行行的完整代码

```c
typedef struct
{
  token_type type;
  uint16_t code_nr;
  hkey_t key;
  // store code_nr when type is NUMBER
  // store identifier when type is IDENTIFIER
  // when key.string != NULL, key stores the label string
} label_t;

typedef struct
{
  token_type type;
  uint32_t data;
  string_t literal;
  // store idx for MEM | ATTR_LOWARG | ATTR_HIGHARG
  // store value for NUMBER | TRAP | TRACE | ERRNO
} obj_t;

typedef struct
{
  obj_t left_var;
  token_type operator;
  obj_t right_var;
  // if operator is NEGATIVE, then it should be A EQUAL NEGATIVE A
  // but EQUAL is skipped
} assign_line_t;

typedef struct
{
  // token_t if;
  // jump_line_t must starts with if, so skip it
  bool if_bang;
  // if match '!' before jump_condition
  bool if_condition;
  // does condition exists
  // if true, jt and jf both uint16_t
  // else jt is uint32_t, jf is ignored

  // obj_t A;
  // jump always compare A with something else, so skip it
  token_type comparator;
  obj_t cmpobj;

  label_t jt;
  label_t jf;
  // pc += (jump_condition ? jt : jf) + 1
  // pc += jt + 1
} jump_line_t;

typedef struct
{
  // token_type return
  // return_line_t must have return, so skip it
  obj_t ret_obj;
} return_line_t;

typedef void *empty_line_t;
typedef void *eof_line_t;

typedef struct
{
  char *error_start;
  char *error_msg;
} error_line_t;

typedef enum
{
  ASSIGN_LINE,
  JUMP_LINE,
  RETURN_LINE,
  EMPTY_LINE,
  EOF_LINE,
  ERROR_LINE,
} expr_type;

typedef struct
{
  expr_type type;
  string_t label_decl;
  char *line_start;
  uint16_t text_nr;
  uint16_t code_nr;
  uint16_t comment;
  uint16_t line_len;

  union
  {
    assign_line_t assign_line;
    jump_line_t jump_line;
    return_line_t return_line;
    empty_line_t empty_line;
    eof_line_t eof_line;
    error_line_t error_line;
  };
} statement_t;
```

#### AST
在比seccomp更复杂的语言中，为了各种表达式，会使用到AST语法树的概念。但由于这个概念还是很有趣的，所以介绍下。

考虑如下的表达式。
`uint32_t a *= (b + c.num);`
他的AST树大致是下面这样(顺便提一嘴，gpt的生图貌似不太行，claude的免费模型用svg生图倒还行)
![ast](./c-handler/ast.png)

### resolve
resolve阶段可以做非常多的事情，因为这个阶段在parse后，也就是我们对用户代码已经达成了完全的理解。
所以可以做一些语义检查(parse阶段只有语法检查)，做一些变量，标签的绑定(通过hash查找)

比如在parse阶段，我们看到一个标签的declaration，这时候我们将标签和相关信息插入哈希表。
在resolve阶段，我们就可以根据标签的reference来在哈希表中进行查找。

### 心得
说是心得，其实就是最近写代码的一些小巧思

#### enum数组
```c
  // ARCH_X86 : TOKEN_EOF
  for (uint32_t enum_idx = (int)ARCH_X86; enum_idx < (int)UNKNOWN; enum_idx++)
    {
      if (match_string (token_pairs[enum_idx], strlen (token_pairs[enum_idx])))
        INIT_TOKEN (enum_idx);
    }
```
请把这段代码和上面的`token_type`和`token_pairs`联系起来。
这里的小巧思是将部分token的实际内容放进`token_pairs`，并且在循环中用索引来索引enum。当enum_idx = ARCH_X86时，token_pairs[enum_idx]的值就是"i386"，再将其和用户代码进行比较。
用了非常简洁的几行代码完成了对大部分固定内容的token的扫描。当然必须承认的是这种简洁的代价是一定的效率，无脑的使用match_string进行字符串比较的效率并不高，但能节省下很多重复的代码。

在scan中第一次尝到好处后，我就开始推广(滥用)enum数组了
下面是另一个简单的案例，我将无关代码抽离了，这样更清晰一些
这样一个本来需要使用好几个switch_case的重复判断就被简化成了简单的取数组。
取数组的效率明显比进行多次的switch_case高对吧

但仍需要注意一点，使用这种技巧必须考虑到是否可能出现数组越界。在这里由于resolve已经检查过了，所以我就可以假设ret_type符合我的预期，不会出现数组越界。就算出现ret_type不符合预期的情况，也是resolve的检查缺失问题，这段代码本身是没有问题的(代码的去耦合真是太好啦！)
```c
static uint32_t retvals[] = {
  [KILL_PROC] = SCMP_ACT_KILL_PROCESS,
  [KILL] = SCMP_ACT_KILL,
  [ALLOW] = SCMP_ACT_ALLOW,
  [NOTIFY] = SCMP_ACT_NOTIFY,
  [LOG] = SCMP_ACT_LOG,
  [TRACE] = SCMP_ACT_TRACE (0),
  [TRAP] = _SCMP_ACT_TRAP (0),
  [ERRNO] = SCMP_ACT_ERRNO (0),
};

f.k = retvals[ret_type] 
```

总结下来说，这种enum的技巧像是把一些固定的简单逻辑从代码中抽离，将其放到了数组中，用取的操作替换了传统的switch_case语句

#### 更进一步！
仅仅通过enum数组取数据还是太保守啦！我在负责打印的代码(src/decoder/formatter.c)中使用了enum数组取函数指针。这部分也是我最满意的部分，代码简洁，可维护性高，效率也不差

区区80行代码就完成了对ceccomp中各种token的带颜色打印。要知道带颜色打印一直是很让人头疼的事情。
这里通过enum数组完成了对各种obj的打印方法和颜色的统一管理，而各个函数的逻辑也都很简单。
假设想要更改某种obj的打印方法/颜色都很简单，只需要更改obj_print数组的内容就行。
同时还复用了token_pairs数组来打印固定内容token(token_pairs的设计也是我认为很满意的，能将enum和token字符串进行转换的操作在整个仓库中都提供了很大便利)
```c
typedef void (*print_fn) (obj_t *obj);

typedef struct
{
  print_fn handler;
  char *color;
} obj_print_t;

static void
print_num (obj_t *tk)
{
  if (tk->literal.start != NULL)
    fprintf (fp, "%.*s", tk->literal.len, tk->literal.start);
  else
    fprintf (fp, "0x%x", tk->data);
}

static void
print_str (obj_t *tk)
{
  fprintf (fp, "%s", token_pairs[tk->type]);
}

static void
print_identifier (obj_t *tk)
{
  fprintf (fp, "%.*s", tk->literal.len, tk->literal.start);
}

static void
print_dec_bracket (obj_t *tk)
{
  fprintf (fp, "%s", token_pairs[tk->type]);
  fprintf (fp, "[%d]", tk->data);
}

static void
print_hex_bracket (obj_t *tk)
{
  fprintf (fp, "%s", token_pairs[tk->type]);
  fprintf (fp, "[0x%x]", tk->data);
}

static void
print_paren (obj_t *tk)
{
  fprintf (fp, "%s", token_pairs[tk->type]);
  fprintf (fp, "(%d)", tk->data);
}

obj_print_t obj_print[] = {
  [A] = { print_str, BRIGHT_YELLOWCLR },
  [X] = { print_str, BRIGHT_YELLOWCLR },

  [MEM] = { print_hex_bracket, BRIGHT_YELLOWCLR },
  [ATTR_LOWARG] = { print_dec_bracket, BRIGHT_BLUECLR },
  [ATTR_HIGHARG] = { print_dec_bracket, BRIGHT_BLUECLR },

  [ATTR_SYSCALL] = { print_str, BRIGHT_BLUECLR },
  [ATTR_ARCH] = { print_str, BRIGHT_BLUECLR },
  [ATTR_LOWPC] = { print_str, BRIGHT_BLUECLR },
  [ATTR_HIGHPC] = { print_str, BRIGHT_BLUECLR },
  [IDENTIFIER] = { print_identifier, BRIGHT_CYANCLR },

  [NUMBER] = { print_num, BRIGHT_CYANCLR },

  [KILL_PROC] = { print_str, REDCLR },
  [KILL] = { print_str, REDCLR },
  [ALLOW] = { print_str, GREENCLR },
  [NOTIFY] = { print_str, YELLOWCLR },
  [LOG] = { print_str, YELLOWCLR },
  [TRACE] = { print_paren, YELLOWCLR },
  [TRAP] = { print_paren, YELLOWCLR },
  [ERRNO] = { print_paren, REDCLR },
};

static void
obj_printer (obj_t *obj)
{
  if (color_enable)
    fprintf (fp, "%s", obj_print[obj->type].color);
  obj_print[obj->type].handler (obj);
  if (color_enable)
    fprintf (fp, "%s", CLR);
}
```

### v4.0
这篇博客写的时候，ceccomp已经完成了这次的major refactor。我们预期会在近期进行一些测试，修复未知的小bug，随后争取在Ubuntu发版前发布我们的v4.0稳定版本，这样Ubuntu用户也可以用到经过重构后的Ceccomp
