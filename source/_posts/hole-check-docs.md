---
title: Hole elimination docs in V8(翻译)
date: 2026-05-28 17:22:38
categories: chrome/v8研究
tags: [ TDZ, v8 ]
---

最近看到v8的docs中更新了对于TDZ hole elimination的各种处理. 让ai翻译了转载下. 
有些表述性的问题, 但整体来说是很优质的解析.

# V8 中的 Hole Check Elision

Hole check elimination（TDZ check elimination，TDZ 检查消除）是 V8 中一个多阶段流水线：它在保证 Temporal Dead Zone（TDZ）语义正确的同时优化性能。

## 什么是 Hole Check？

在 JavaScript 中，块级作用域变量（`let` 和 `const`）受 Temporal Dead Zone（TDZ）约束。变量初始化前访问它会导致 `ReferenceError`。V8 通过在访问点插入 “hole check” 来实现这一点：检查变量当前是否持有特殊的 `TheHole` 值（表示尚未初始化），如果是则抛出异常。

> [!NOTE]
> **关于示例的说明**：这些文档中的示例经常使用 “怪异” 或不常见的 JavaScript 写法，例如用 `// let x = hole` 注释表示未初始化状态，或者把声明放在不寻常的位置。这是为了刻意展示 V8 的内部分析方式，即使这些代码在标准执行中可能会无条件抛出 `ReferenceError`。

### 1. 简单情况（不需要检查）

如果变量在一个简单线性流程中、按词法位置出现在初始化之后才被访问，V8 知道它是安全的，因此不需要发出检查。

```javascript
function success() {
  let x = 10;
  console.log(x); // 安全！不需要检查。
}
```

### 2. TDZ 情况（需要检查）

如果变量在词法声明之前被访问，它一定处在 TDZ 中，并且总会抛出异常。

```javascript
function tdz() {
  console.log(x);
  let x = 10;
}
```

### 3. 不确定情况（动态控制流）

当控制流发生分支时，静态判断变量是否已经初始化会变得更困难。

```javascript
function testUncertain(cond) {
  // 捕获 x 的闭包
  const mightFail = () => x;

  if (cond) {
    // 在 x 初始化之前执行 -> ReferenceError (TDZ)
    mightFail();
  }

  let x = 10; // 初始化器

  // 在 x 初始化之后执行 -> 安全！
  mightFail();
}
```

## 三阶段流水线

为了处理不同复杂度的场景，V8 使用多阶段方法：

1. **[步骤 1：Parser / AST 作用域分析](hole-check-elimination-parser.zh.md)**：基于作用域规则和投影后的源码位置，静态计算变量是否“曾经”需要 hole check。
2. **[步骤 2：解释器（Ignition）](hole-check-bytecode.zh.md)**：在字节码生成期间执行局部控制流分析，从而在同一函数内消除冗余检查。
3. **[步骤 3：优化编译器（Maglev / Turboshaft）](hole-check-optimized.zh.md)**：执行更高级的全局控制流和逃逸分析，消除热代码中剩余的 hole check。

# Parser 中的 Hole Check Elimination

本文说明 V8 如何解析变量、执行 Temporal Dead Zone（TDZ）规则，以及如何使用缓存机制优化查找，同时不破坏源码位置计算。

## 简单的函数内访问（基线）

在考虑复杂的作用域链遍历之前，最简单的场景是在变量声明所在的同一个作用域中访问该变量。

对于没有嵌套闭包的简单同作用域局部变量访问，V8 会直接比较变量引用的纯源码位置和变量的 `initializer_position`。如果访问在词法上发生在初始化器之前，或者恰好位于初始化器位置，就需要 hole check。传播后的 `access_position` 这个概念实际上**只与 `eval` 和嵌套闭包（包括类）有关**。对于简单的函数内访问，原始源码位置就足够了。

```javascript
function simple() {
  console.log(x); // access_position < initializer_position -> 需要 TDZ 检查
  let x = 10;     // initializer_position
  console.log(x); // access_position > initializer_position -> 不需要检查
}
```

> **字节码生成说明**：Parser 通过给 `VariableProxy` 标记 `HoleCheckMode`（`kElided` 或 `kRequired`）把这个决策传给字节码生成器。如果标记为 `kElided`，字节码生成器会完全跳过 hole check 指令。

## 跨闭包和 Eval 访问

一旦引入函数提升和 `eval` 这样的 JavaScript 语言特性，简单的原始位置方法就会失效。传播后的 `access_position` 在这里变得非常重要。

### 嵌套闭包的挑战

函数声明会被提升到其作用域顶部（见 [FunctionDeclarationInstantiation](https://tc39.es/ecma262/#sec-functiondeclarationinstantiation)），而类声明不会提升（见 [BlockDeclarationInstantiation](https://tc39.es/ecma262/#sec-blockdeclarationinstantiation)）。这会造成词法顺序和执行顺序之间的差异。

**示例：函数声明与未提升闭包**

```javascript
function testHoisting() {         // 外层作用域（从 Pos 20 开始）
  // let x = hole
  inner();
  let x = 10;                     // initializer_position = Pos 65

  // 函数声明会被提升。
  function inner() {              // 内层作用域（从 Pos 140 开始）
    console.log(x);               // hole check 的原始 access_position = Pos 160
                                  // 作用域遍历后的 access_position = Pos 20
  }

  // 未提升闭包（例如类或函数表达式）不会被提升。
  class MyClass {                 // 类作用域（从 Pos 200 开始）
    method() {
      console.log(x);             // hole check 的原始 access_position = Pos 240
                                  // 作用域遍历后的 access_position = Pos 240
    }
  }
}
```

**原始位置和提升之间的问题**

在上面的 `testHoisting` 示例中，函数 `inner` 被提升。它在第 35 行被调用，发生在第 36 行 `x` 初始化之前。但是，`inner` 内部访问 `x` 的原始源码位置（第 40 行，Pos 160）在词法上位于 `x` 初始化位置（第 36 行，Pos 65）之后。

如果 V8 只依赖这些原始源码位置，就会错误地认为 Pos 160 的访问发生在 Pos 65 的初始化之后，从而消除本来必需的 hole check。

### 解决方案：传播 `access_position`

为了解决这个问题，当 V8 在嵌套闭包中遇到变量访问时，会通过递归向外遍历作用域链来解析引用，并在遍历过程中更新 `access_position`。这个调整后的位置会把内部访问投影到外层作用域的边界上。

**`access_position` 如何解决提升问题：**

当 V8 走出一个作用域时，会检查这个作用域边界是否被提升。如果被提升，就会更新 `access_position` 来反映这一点。由于提升函数可以被提前调用，该访问实际上会被投影到外层作用域的最开始位置。

**在 `inner` 内部 `console.log(x)` 查找 `x` 的轨迹（已提升）：**

```text
[Scope Walk] 当前作用域：`inner`
  - 目标             : 'x'
  - access_position  : 160（原始源码位置）
  - 结果             : 未找到。继续向外遍历...

[Scope Walk] 穿过边界（`function inner()`）
  - 边界类型         : 已提升函数
  - access_position  : 从 160 更新为 20（投影到外层作用域起点）

[Scope Walk] 当前作用域：`testHoisting`
  - 结果             : 找到 `let x`（initializer_position: 65）

[TDZ Check]  initializer_position (65) >= access_position (20)
  - 结论             : TRUE（需要 hole check！）
```

**在 `MyClass` 内部 `console.log(x)` 查找 `x` 的轨迹（未提升）：**

```text
[Scope Walk] 当前作用域：`MyClass`
  - 目标             : 'x'
  - access_position  : 240（原始源码位置）
  - 结果             : 未找到。继续向外遍历...

[Scope Walk] 穿过边界（`class MyClass`）
  - 边界类型         : 未提升类
  - access_position  : 不变（仍为 240）

[Scope Walk] 当前作用域：`testHoisting`
  - 结果             : 找到 `let x`（initializer_position: 65）

[TDZ Check]  initializer_position (65) >= access_position (240)
  - 结论             : FALSE（不需要 hole check）
```

> **字节码生成说明**：对于确实需要 hole check（`kRequired`）的引用，Parser 还会传达目标是否位于**同一闭包或不同闭包**。这是因为字节码编译器会对局部定义的变量（同一闭包中的变量）执行自己的局部控制流分析，以获得更精确的 hole check 消除。理论上这可以扩展到跨闭包变量，但 V8 目前把这类追踪限制在同一闭包中，这是一个**实现决策**（部分原因是为了让分析保持轻量，并受限于 64 位位图）。

## 高级闭包：`is_hoisted_in_context`

虽然沿着物理作用域链遍历可以自然处理提升，但它会与两个性能特性发生冲突：

1. **惰性编译**：延后编译函数时，变量解析结果必须与立即编译一致。
2. **作用域消除**：移除不需要 context 分配的中间作用域，以缩短 context 链。

**交汇示例：**

为了理解这些特性如何冲突，考虑一个返回内部函数的提升函数：

```javascript
function outer() {
  // 1. 执行 `hoisted()` 并立即调用它返回的值（`inner()`）。
  // 这发生在 `x` 初始化之前，因为 `hoisted` 被提升到了顶部。
  hoisted()();

  let x = 10;

  function hoisted() {
    // 2. 被消除的作用域：V8 消除这个作用域，因为 `hoisted` 自身没有
    // 需要 context 分配的变量。

    return function inner() {
      // 3. 惰性编译单元：`inner` 会在调用时稍后编译。
      // 编译时，它会解析对 `x` 的引用。
      console.log(x); // ReferenceError (TDZ)
    };
  }
}
```

**问题：**

提升函数（`hoisted`）的作用域会被 V8 消除，以保持 context 链较短。但是它包含一个会被惰性编译的内部单元（`inner`）。因为外层函数是提升的，这个内部单元中的代码可以提前执行。当这个内部单元最终被编译时，它包含的任何指向提升函数外部变量（如 `x`）的引用都必须被正确解析。

**修复：**

由于中间作用域被消除了，通常用于告诉我们应更新这些引用的 `access_position` 的物理边界已经不存在。为了解决这个问题，V8 会把惰性编译单元 `inner` 的作用域上的 `is_hoisted_in_context` 标志设为 `true`。

虽然 `inner` 是函数表达式，并不会在它自己的外层作用域（`hoisted`）中按词法提升；但由于 `hoisted` 的作用域被消除了，运行时 context 链会把 `inner` 直接连接到 `outer`。

**运行时 Context 链（编译 `inner` 时）：**

```text
[ inner() Scope ]  ========>  [ outer() Context ]
                       ^
                       | （`hoisted()` 作用域完全不存在！）
```

在这个**运行时 context** 中，`inner` 会提前执行，因为它的父函数是被提升的。`is_hoisted_in_context` 标志正是捕获这一点：它告诉 `inner`，虽然它自身在词法上没有提升，但相对于它运行时看到的 context，它是被提升的。这个标志让 `inner` 在延迟编译期间把 `access_position` 更新为外层 **context** 的起始位置；在这个具体例子中，也就是 `outer()` 的起始位置。

*（注意：这个标志也必须存储在 `SharedFunctionInfo`（SFI）上。未编译函数在编译前没有自己的 `ScopeInfo`，但它们仍然需要知道其内部作用域相对于外层 context 的行为。）*

## 标准缓存与陈旧位置问题

每次变量访问都遍历作用域链代价很高（每次访问 O(N)）。为了优化这一点，V8 会在跨编译单元边界的标准词法变量上缓存已解析的作用域。这发生在内部函数被惰性编译，并引用已经编译过的外部函数变量时。V8 使用外部函数编译期间生成的 `ScopeInfo` 来解析这些变量。这个解析结果会通过 **`cache_scope`** 直接缓存在编译单元边界上。

### 冲突：陈旧的 `access_position`

当作用域遍历因为命中 `cache_scope` 而被短路时（因为从之前查找或外层 `ScopeInfo` 中找到缓存解析结果），递归遍历会被跳过。直接后果是传给 hole-check 逻辑的 `access_position` 是“陈旧”的：由于中间作用域被跳过，它**没有**被这些中间作用域调整。

如果 V8 依赖这个陈旧的 `access_position` 重新计算是否需要 hole check（`var->initializer_position() >= access_position`），结果就会出错。

### 解决方案：缓存 `HoleCheckState`

为了避免依赖损坏的、未调整的 `access_position`，V8 会在**第一次**完整作用域遍历期间，把 hole check 计算的**结果**直接缓存在变量上（`HoleCheckState::kForce` 或 `kSkip`）。之后的查找会完全绕过 `access_position` 计算。

## `eval` 作用域机制

为了理解为什么 `eval` 会让 hole check elision 复杂化，有必要先回顾按 ECMAScript 规范，`eval` 内部声明的变量如何确定作用域：

### 直接 `eval`（Sloppy Mode）

当直接调用 `eval()` 且没有启用严格模式时：

- **`var` 声明**：从 `eval` 中提升出去，并加入外层函数的变量声明作用域（经常落到 `VarBlock` 或函数作用域自身中，从而引入 `DynamicLocal` 行为）。
- **`let` 和 `const` 声明**：严格保留在 `eval` 代码块自己的作用域内，不会泄漏到外层函数。

### 直接 `eval`（Strict Mode）

当直接调用 `eval()` 且启用了严格模式时（无论是 eval 字符串内部有 `'use strict'`，还是外层代码处于严格模式）：

- **所有声明**（`var`、`let`、`const` 和函数）都严格保留在 `eval` 的本地作用域中，绝不会泄漏到外层函数。（是的，严格模式 `eval` 中可以声明 `var`，但它仍然局部于 `eval` 执行上下文。）

### 间接 `eval`

当间接调用 `eval` 时（例如 `(0, eval)("...")`，或者把 `eval` 赋给变量再调用）：

- 执行上下文总是**全局作用域**（或模块作用域），而不是本地函数作用域。
- **Sloppy mode**：`var` 声明会泄漏到全局对象。
- **Strict mode**：所有声明都保留在 `eval` 作用域本地。

> **性能说明**：这种行为的存在是为了支持**静态 `eval` 检测**。如果间接 `eval` 调用也能污染本地函数作用域，V8 就必须保守地假设**任何**函数调用（它可能是别名化的 `eval`）都可能动态引入变量！这会阻止几乎所有局部变量优化。通过把本地作用域污染限制到可静态检测的**直接** `eval` 调用，V8 保住了全局性能。

## Sloppy Eval 和 `DynamicLocal`

当函数体包含 sloppy `eval` 时，V8 无法静态知道它会在运行时访问或引入哪些变量。由于 `eval` 可能动态引入一个作为 context extension 的遮蔽变量，这个闭包内的查找必须动态处理。

为了解决这一点，V8 引入了 **`DynamicLocal`** 变量模式。V8 会把底层静态已知的词法目标作为后备，缓存在名为 **`local_if_not_shadowed`** 的属性中。

*（注意：`with` 语句也会引入动态作用域。但对于 `with`，V8 会退回到纯 `Dynamic` 变量并发出 `LdaLookupSlot`，这会无条件调用 runtime，没有 fast path！）*

### 示例 1：Eval 的挑战

```javascript
function testEval() {
  eval("console.log(y)"); // 抛出 ReferenceError！'y' 处在 TDZ 中。
  let y = 20;
}
```

`eval` 字符串内部 `console.log(y)` 的源码位置是 `0`（相对于字符串起点）。如果 V8 在外层作用域中查找 `y` 时使用这个原始位置 `0`，它几乎总是会显得位于外层变量声明之前，从而触发不必要的 hole check（即使 `eval` 是在变量初始化之后调用的！）。

为了解决这个问题，当 V8 的作用域遍历穿出 `eval` 作用域边界时，它会简单地把内部原始 `access_position`（可能是 `0`）替换成外层作用域中 `eval()` 调用的精确源码位置。从那时起，这次访问就会被正确地视为好像物理上发生在 `eval()` 被调用的位置！

### 示例 2：可视化 `local_if_not_shadowed`

我们可以把 `DynamicLocal` 概念“伪加入”到 JavaScript 代码里，以可视化它如何链接到外层变量：

```javascript
function outer() {
  // let x = hole

  function inner(str) {
    eval(str); // 可能引入一个遮蔽用的 'var x'

    // 从概念上看，V8 在这里把 'x' 看作：
    // Proxy(x) -> DynamicLocal [local_if_not_shadowed -> Variable(x in outer)]
    console.log(x);
  }

  let x = 10; // 静态解析出的外层变量
}
```

在这个场景中，`inner` 内部对 `x` 的访问会变成 `DynamicLocal`。V8 会把来自 `outer` 作用域的 `x` 缓存在 `local_if_not_shadowed` 中。如果 `str` 在运行时没有声明 `var x`，V8 就会退回去读取外层作用域中缓存的 `x`。

---

### 底层变量能否位于与 `eval` 相同的闭包中？

不能。为了理解原因，必须先明确 `DynamicLocal` 变量在哪里被引入：如果某个函数体在闭包内包含 `eval` 调用，它们会被创建在**函数体的声明作用域**中。这是因为 `eval` 可能在运行时向该声明作用域动态引入变量，从而遮蔽已有变量。

基于这一点，我们看看 V8 在这个场景中如何处理不同变量模式：

- **对于 `let` 和 `const`**：`eval` 只能向外层作用域引入 `var` 声明（因为 `let` 和 `const` 严格保留在 `eval` 自身内部）。如果同一闭包作用域中已经有一个 `let` 或 `const` 变量，那么通过 `eval` 引入同名 `var` 在 JavaScript 中是 **SyntaxError**。因此，一个表示 TDZ 变量的合法 `DynamicLocal` 永远不能在同一闭包中被 `eval` 遮蔽。
- **对于普通 `var`**：如果 `eval` 引入与同一闭包中已有 `var` 同名的 `var`，V8 会直接解析或合并它们，而不是创建 `DynamicLocal`。
- **对于 `VarBlock` 作用域**：`VarBlock` 是一种充当声明作用域的块作用域。V8 在**类静态块**和**带非简单参数的函数**中使用它。由于类总是严格模式，类静态块中的 `eval` 不能引入动态变量，因此不需要 `DynamicLocal`。对于带非简单参数的函数，`VarBlock` 函数体中的 `DynamicLocal` 可能指向位于它外部但仍在同一闭包内的变量（例如函数参数）。不过这些参数在 V8 中总是 `kCreatedInitialized`，也就是说它们**永远不需要 hole check**！

因此，对于任何实际**需要 hole check** 的变量（即 `let` 和 `const` 变量），被遮蔽的目标一定在不同的外层闭包中！所以这些查找的 `same_closure_scope` 保证为 false。

# 解释器（Ignition）中的 Hole Check Elision

本文介绍 V8 中 Hole Check Elision 流程的第 2 步，重点说明字节码生成器（`src/interpreter/bytecode-generator.cc`）如何执行局部控制流分析，以消除冗余的 TDZ hole check。

## 我们想达成什么

虽然 [Parser](hole-check-elimination-parser.zh.md) 会执行结构性分析，以确定一个变量是否**曾经**需要 hole check，但字节码生成器会执行一种**局部、流敏感分析**，以避免在同一函数内发出冗余的检查字节码。

如果某个变量在线性代码块中被多次访问，或者在初始化有保证的分支之后被访问，那么每次都发出 `ThrowReferenceErrorIfHole` 就很浪费。Ignition 使用局部分析来追踪初始化状态，并消除这些冗余检查。

## 示例说明

为了理解字节码生成器做了什么，我们看看具体的 JavaScript 控制流结构如何影响 hole check elision。

> [!IMPORTANT]
> **为什么这些示例使用闭包包装器（`getX` / `getY`）**：
> 在标准的线性 JavaScript 中，如果局部变量在自己的声明作用域内被直接访问，编译器很容易静态证明访问发生在初始化之前还是之后。如果编译器证明它发生在**之前**，它可以消除检查并无条件抛出 `ReferenceError`（或者静态优化它）。如果它发生在**之后**，它可以安全地完全删除检查。
>
> 为了迫使编译器一开始就生成一个**动态 hole check**（`ThrowReferenceErrorIfHole` 字节码），我们必须让编译器无法静态预测执行顺序。把访问包装在逃逸闭包里（`const getX = () => x`）正好能做到这一点。由于编译器无法静态知道闭包何时被调用，它被迫在闭包内部发出动态 hole check。因此，这些示例中的包装函数（例如 `runIfElseTest`）和内部闭包对于展示 V8 字节码生成器如何跨不同执行路径动态追踪并消除这些检查是**必不可少的**。

### 1. `if` / `else`（分支与汇合）

```javascript
function runIfElseTest() {
  function testIfElse(cond) {
    const getX = () => x; // 捕获 x 的闭包
    const getY = () => y; // 捕获 y 的闭包

    if (cond) {
      console.log(getX()); // 1. 需要检查 'x'。
      console.log(getX()); // 2. 再次访问 'x'。检查被消除！
    } else {
      console.log(getX()); // 3. 需要检查 'x'。
      console.log(getY()); // 4. 需要检查 'y'。
    }

    // --- 汇合点 ---
    // 'x' 在两个分支中都被检查过 -> 保证已初始化。
    // 'y' 只在 else 分支中被检查过 -> 无法保证。

    console.log(getX()); // 5. 在这里访问 'x'。检查被消除！
    console.log(getY()); // 6. 在这里访问 'y'。仍然需要检查！
  }

  let x = 10;
  let y = 20;
}
```

### 2. 循环（`break` 和 `continue`）

循环带来挑战，因为执行会重复，而且如果条件一开始就是 false，循环体可能完全不会执行。

**字节码生成中的关键约束：**

1. **单遍分析**：字节码生成器以单遍方式遍历 AST。它不会执行迭代式数据流分析来寻找不动点（例如判断第一轮迭代后什么会变成已初始化）。
2. **零次迭代可能性**：由于循环条件一开始可能为 false，V8 不能保证循环体至少执行一次。

因此，循环内部执行过的任何 hole check 都会在循环结束后被保守地忘记。

```javascript
function runLoopTest() {
  function testLoop(arr) {
    const getX = () => x; // 捕获 x 的闭包

    for (let i = 0; i < arr.length; i++) {
      console.log(getX()); // 1. 需要检查 'x'。

      if (arr[i] === 0) {
        continue;     // 'continue' 会为下一次迭代更新知识。
      }

      if (arr[i] === 1) {
        break;        // 'break' 不会为循环后的作用域更新知识。
      }
    }

    // 即使 'x' 在循环体开头被无条件检查过，
    // V8 也不能保证循环至少运行一次（arr.length 可能是 0）。
    // 因此这里保守地仍然需要检查。
    console.log(getX()); // 2. 访问 'x'。仍然需要检查！
  }

  let x = 10;
}
```

**`next` 表达式的微妙之处：**

对于 `for (init; cond; next) { body }` 这样的标准循环，有一个细节：`body` 内部的 `continue` 语句会跳过循环体剩余部分，但**仍然会执行 `next` 表达式**，然后才开始下一次迭代。

为了保证正确性，V8 会强制所有 `continue` 路径在分析 `next` 表达式之前合并。这样可以确保对 `next` 表达式的分析只依赖于在 `continue` 点之前保证执行过的检查，而不会错误地假设循环体后半部分（被跳过的部分）中的检查仍然有效。

### 3. `switch` 语句

`switch` 语句会产生复杂的非线性控制流。V8 在 `switch` 之后优化检查的能力取决于它是否是**穷尽的**（是否有 `default` 分支）：

- **有 `default`**：V8 知道至少会执行一个分支。它会计算所有分支检查状态的交集。只有在**每个**分支中都执行过的检查（包括 `default`）才会在 switch 后被消除。
- **没有 `default`**：整个 switch 可能被跳过。V8 会保守地丢弃 switch 内部执行的所有检查，并恢复到 switch 前的状态。

#### 示例：穷尽性与 fallthrough

```javascript
function runSwitchTest() {
  function testSwitch(val) {
    const getX = () => x; // 捕获 x 的闭包
    const getY = () => y; // 捕获 y 的闭包

    switch (val) {
      case 1:
        console.log(getX()); // 1. 需要检查 'x'。
        // Fall through 到 case 2！
      case 2:
        console.log(getX()); // 2. 仍然需要检查！（可以直接跳到这里）
        console.log(getY()); // 3. 需要检查 'y'。
        break;
      default:
        console.log(getX()); // 4. 需要检查 'x'。
        console.log(getY()); // 5. 需要检查 'y'。
    }

    // --- 汇合点 ---
    // 由于存在 default，状态会被合并。
    // 'x' 在所有路径上都被检查过：路径 1->2、直接进入路径 2、以及 default 路径。
    // 'y' 在所有路径上都被检查过：路径 1->2、直接进入路径 2、以及 default 路径。

    console.log(getX()); // 6. 访问 'x'。检查被消除！
    console.log(getY()); // 7. 访问 'y'。检查被消除！
  }

  let x = 10;
  let y = 20;
}
```

注意这个示例中两个关键细节：

1. **在 switch 内部**：`case 1` 中对 `x` 的检查**不会**消除 `case 2` 中的检查。因为程序可以直接跳到 `case 2`（绕过 `case 1`），V8 会从 switch 前的状态开始分析每个 `case` 分支。
2. **在 switch 之后**：由于存在 `default`，并且所有路径都检查了两个变量，因此两个变量在 switch 后都被认为是安全的。如果删除 `default`，V8 会保守地假设整个 switch 被跳过，那么第 6 行和第 7 行的两次访问都需要检查。

### 4. 标号块与 `break`

标号块允许使用指向该标签的 `break` 语句提前退出任意代码块。这会在块尾汇合点产生多条路径。

V8 通过把显式 `break` 路径和正常 fallthrough 完成路径都视为共识合并中的分支来处理这一点。

#### 示例：带条件 Break 的标号块

```javascript
function runLabeledBlockTest() {
  function testLabeledBlock(cond) {
    const getX = () => x; // 捕获 x 的闭包
    const getY = () => y; // 捕获 y 的闭包

    my_label: {
      console.log(getX()); // 1. 需要检查 'x'。

      if (cond) {
        console.log(getY()); // 2. 需要检查 'y'。
        break my_label; // 跳出该块！
      }

      // 路径 A：没有 break 的正常完成。只检查过 'x'。
    }

    // --- 汇合点 ---
    // 路径 A（Fallthrough）：只检查过 'x'。
    // 路径 B（Break）：检查过 'x' 和 'y'。
    // 交集：只有 'x' 被认为安全。

    console.log(getX()); // 3. 访问 'x'。检查被消除！
    console.log(getY()); // 4. 访问 'y'。仍然需要检查！
  }

  let x = 10;
  let y = 20;
}
```

### 5. `try` / `catch` / `finally`

```javascript
function testTryCatch() {
  const getX = () => x; // 捕获 x 的闭包
  const getY = () => y; // 捕获 y 的闭包

  try {
    console.log(getX()); // 需要检查。
    // 这里可能抛出异常...
    console.log(getY()); // 需要检查。
  } catch (e) {
    console.log(getX()); // 需要检查。
  }

  // --- 汇合点 ---
  // 'x' 在 try 和 catch 中都被检查过 -> 可消除。
  // 'y' 可能在 try 中抛出异常之前没有执行到 -> 仍然需要。

  console.log(getX()); // 检查被消除！
  console.log(getY()); // 仍然需要检查！
}

let x = 10; // 外层作用域中的初始化器
let y = 20; // 外层作用域中的初始化器
```

---

## 底层机制：64 位位图

为了实现上面展示的优化，V8 使用一个 64 位整数 `hole_check_bitmap_` 来追踪变量的分析状态。（这会把追踪限制到每个作用域 64 个变量，但这个界限足以覆盖绝大多数实际情况。）

- 每一位对应一个变量索引（最多 64 个变量）。
- 位值为 `1` 表示该变量在当前执行路径上已经被检查或初始化。
- 当变量已知安全时，同一块中的后续访问会跳过 `ThrowReferenceErrorIfHole` 字节码的发出。

为了在跨控制流时正确维护这个位图，V8 使用两种主要策略：

### 1. 作用域化状态保存（`HoleCheckElisionScope`）

对于没有保证替代路径的条件执行控制流分支（例如没有 `else` 的简单 `if` 语句），V8 通过在进入时保存位图状态、退出时恢复位图状态来保证正确性。

- **动作**：生成器把当前位图状态保存到栈上。
- **效果**：在汇合点处，生成器的活动位图被设置为交集结果。只有当某个变量在通往该点的**所有**可能路径上都被检查过时，它才会在汇合点之后被认为安全。

---

# 优化编译器中的 Hole Check Elision

本文介绍 V8 中 Hole Check Elision 流程的第 3 步，重点说明优化编译器（Maglev 和 Turboshaft/TurboFan）如何追踪变量并消除 Temporal Dead Zone（TDZ）hole check。

## Maglev：高层流敏感追踪

Maglev 是 V8 的中层优化编译器。它在图优化阶段使用一种专门的高层方法来消除 hole check。

### 机制

- **IR 表示**：Maglev 使用专门的 `ThrowReferenceErrorIfHole` 节点显式表示 TDZ 检查。
- **Holiness 分析**：优化期间，Maglev 使用 `ValueNode::IsTheHole()` 方法递归检查一个值的来源（展开 identity、检查 phi 输入等）。它返回一个 `Tribool` 状态：
  - `kTrue`：该值确定是 `TheHole`。
  - `kFalse`：该值确定不是 `TheHole`。
  - `kMaybe`：分析无法确定。
- **消除**：在 `MaglevGraphOptimizer` 中访问 `ThrowReferenceErrorIfHole` 节点时：
  - 如果 `IsTheHole()` 返回 `kFalse`，检查节点会从图中完全移除。
  - 如果返回 `kTrue`，它会被替换成无条件抛出。
  - 如果返回 `kMaybe`，检查会被保留。

这种方法让 Maglev 无需运行沉重的通用分析 pass，也能快速有效地删除它知道安全的变量检查。

### Maglev 的隐式控制流消除

因为 Maglev 会构建图，并在环境中追踪变量的当前值，所以当分支被剪枝时，即使没有显式追踪 “holiness” 的流敏感状态，它也能自然地消除 hole check。

**场景：**

考虑一种情况：字节码生成器（步骤 2）必须保留一个 hole check，因为某条路径没有初始化变量：

```javascript
function runExampleTest() {
  function example(cond) {
    const getX = () => x; // 捕获 x 的闭包
    if (cond) {
      // ...
    }
    // 这里的 TDZ 检查是不明确的，因为我们不知道 example 何时被调用！
    console.log(getX()); // 需要检查！
  }

  let x = 10;
}
```

如果 Maglev 专门化这个函数并证明 `cond` 总是 true（例如通过类型反馈），它会从图中剪掉 `else` 分支。

在 baseline 字节码中，`if/else` 之后的访问是一个汇合点，因此必须加载 merge 之后的任意结果值。但在 Maglev 中，由于 `else` 分支消失，merge 也随之消失！最终 `console.log(x)` 处的 `x` 值现在会直接映射到 `then` 分支中的常量 `10`。

当 `MaglevGraphOptimizer` 访问这次加载的检查时，`ValueNode::IsTheHole()` 会查看定义（常量 `10`）并返回 `kFalse`。该检查就会被成功消除！

### 通过 Hole Elision 和 `maybe_assigned` 进行常量追踪

Maglev 利用 hole check elision 和 `maybe_assigned` 标志的强大组合，为 context 分配的变量启用**常量追踪**：

1. **Hole Check 保证**：当变量在 `try`/`catch` 代码块外被访问时，通过 hole check 意味着变量已经安全初始化。如果它是 hole，执行就已经中止了。
2. **不可变性保证**：如果 Parser 把变量标记为**不是 `maybe_assigned`**，Maglev 就知道闭包中的代码不会在初始化后修改它。

**组合效果**：结合这两个事实，Maglev 可以安全地假设第一次成功访问/检查之后，变量值会**永久固定**。这让 Maglev 可以把加载专门化为图中的常量，从而在函数剩余部分同时消除 context load 和后续所有 hole check！

### `try` / `catch` 的挑战

在 `try`/`catch` 代码块内部，这个推理会更复杂，因为抛出异常后执行**确实会继续**（进入 `catch` 块）。

- 如果 `try` 中某个操作因为变量是 hole 而抛出异常，`catch` 块会执行。
- 在 `catch` 块中，我们实际上可能知道该变量**一定**是 hole（因为这就是抛出的原因！）。
- 为了在这些非线性跳转中保持正确性，Maglev 依赖**隐式控制流建模**。Maglev 不会显式构建从 `try` 内每个可能抛出异常的节点到 `catch` 块的控制流边（那会导致图膨胀）。相反，它会在 `catch` 块入口隐式合并 `try` 块内部所有可能抛出指令的环境状态。因此，`catch` 块中每个变量的 “holiness” 状态是所有可能抛出点状态的保守组合（交集）。

#### 示例：Catch 块中的 Hole

```javascript
function testTryCatch() {
  // let x = hole

  try {
    console.log(x); // 抛出 ReferenceError (TDZ)
    x = 10;        // 被跳过！
  } catch (e) {
    // 因为上面的访问抛出异常，我们到达这里。
    // 在这个块中，'x' 保证仍然是 hole！
    console.log(x); // 在这里访问 'x' 会再次抛出异常。
  }

  let x;
}
```

如果 Maglev 盲目假设一次成功访问意味着函数剩余部分都已初始化，它可能会不安全地消除 `catch` 块内的第二次检查。通过在 `catch` 入口强制 spill 并保守合并状态，Maglev 避免了这个陷阱。

> **关于单一抛出路径的说明**：如果 `try` 块中**只有一个**潜在抛出节点，那么合并到 `catch` 块确实是平凡的。在这个特定场景中，Maglev **确实**会绕过交集，直接把抛出节点的精确 frame state 克隆到 `catch` 块中。不过，它仍然**不会**把变量专门化为 “hole 常量”。它只是携带抛出前一刻的状态（例如它**可能**是 hole）。Maglev 缺少路径敏感逻辑，无法推断出“因为我们到达了 catch 块，所以这个特定变量一定是 hole”。

### “反转 Generator” 边界情况

“反转 Generator” 模式打破了线性执行意味着初始化的假设。考虑这个场景：

```javascript
function* f() {
  yield function g() {
    try {
      return test; // 2. 访问外层变量 'test' -> 抛出 TDZ
    } catch (e) {
      gen.next();  // 3. 恢复 generator！
      return test; // 4. 再次访问 'test' -> 成功！
    }
  };
  let test = 10; // 1. 在 yield 之后声明
}

var gen = f();
var g = gen.next().value; // 得到函数 'g'
g(); // 调用 'g'
```

**执行流程：**

1. generator `f()` 暂停在 `yield`，返回函数 `g`。此时 `let test = 10` 还**没有**执行。
2. 调用 `g()`。内部尝试读取 `test`，因为它仍在 TDZ 中，所以抛出 `ReferenceError`。
3. `catch` 块截获错误并调用 `gen.next()`，这会恢复 generator 并执行 `let test = 10`。
4. 现在 `test` 已初始化！`catch` 块返回 `test`，成功读取 `10`。

这里，`g` 内部的访问实际上会通过 `catch` 块**导致**变量被初始化！

为了防止 Maglev 错误地假设执行是线性的，或者错误地认为 `test` 不可能跨 `yield` 从 “hole” 变成 “initialized”，V8 的 Parser 会检测这种模式（在 `try`/`catch` 块内访问从外层 generator 作用域捕获的变量），并**强制把它标记为 `maybe_assigned`**。这会禁用 Maglev 中激进的常量追踪，迫使它采用保守 fallback 行为。

### 内联对 Hole Check 的作用

Maglev 中一个特别强大的 hole check elision 场景发生在**函数内联**期间。

**场景：**

考虑一个内部函数访问外部函数中声明的变量：

```javascript
function outer() {
  let x = 10;

  function inner() {
    console.log(x); // 跨闭包访问
  }

  inner();
}
```

在解析期间（步骤 1），`inner` 内部对 `x` 的访问是跨闭包访问。由于 Parser 不能静态保证闭包执行顺序，它会保守地把该访问标记为需要 hole check（`kRequired`）。在 `inner` 的 baseline 字节码中，会发出一条 `ThrowReferenceErrorIfHole` 指令。

**内联如何改变局面：**

当 Maglev 决定把 `inner()` 内联到 `outer()` 中时，闭包边界实际上消失了。图构建器会把 `inner` 的字节码直接导入 `outer` 的图中。

这种内联把上下文敏感的跨闭包分析转化为标准的局部（过程内）分析。现在，来自 `inner` 的 `x` 访问和 `outer` 中把 `x` 初始化为 `10` 的操作处于**同一张图**中。Maglev 的局部 `ValueNode::IsTheHole()` 分析可以从内联后的访问直接追溯到定义（常量 `10`）。由于这是一个已知的非 hole 常量，检查会在优化代码中被完全消除！

理论上，人们可以执行上下文相关的过程间分析，或使用函数拆分把调用点信息带入被调用方；但内联是 V8 用来解锁这些优化的实际而优雅的机制，它利用了 V8 高度优化的局部编译器图流水线。

## Turboshaft：更底层的通用化规约

Turboshaft（以及历史上的 TurboFan）采用完全不同的思路。它不会为 TDZ 检查维护专门的高层节点，而是很早就把它们降低成标准机器操作，并依赖强大的通用优化 reducer 来清理它们。

### 机制

- **早期降低**：高层 hole check 会被降低成针对 root 值的标准比较：`RootEqual(value, RootIndex::kTheHoleValue)`。这会输入到一个 `BranchOp`，其中 true 分支调用 runtime 抛出错误，false 分支继续执行。
- **通过通用 Reducer 消除**：由于检查被降低成标准条件，Turboshaft 可以使用强大的通用流水线消除它，严格依赖结构化控制流而不是高层类型：
  1. **Branch Elimination（`BranchEliminationReducer`）**：这是 Turboshaft 中消除 hole check 的主要引擎。这些是 Maglev（Turbolev）没有成功消除的检查。该 reducer 以 dominator 顺序处理图，并维护一张 `known_conditions_` 映射。如果执行通过某个 branch 或 `DeoptimizeIf`，证明某个值不是 `TheHole`（即 `RootEqual(...) == false`），该条件就会被记录。之后被这条路径支配、针对同一个值的检查会查询这张映射并立即移除。
  2. **常量折叠（`MachineOptimizationReducer`）**：如果其他优化（例如 store-forwarding）显示该值是某个确定的 heap 常量且不是 hole，该 reducer 会直接把 `TaggedEqual` 比较折叠为 false，从而消除分支。
  3. **没有基于类型的消除**：与 TurboFan 曾经使用的复杂 lattice-based `Type` 系统不同（该系统能把 `TheHole` 理解为一种特定类型），**Turboshaft 的类型系统作用于机器类型**（Word32、Word64 等范围）。它不会在类型里追踪 JS 对象或 `TheHole` 这类特殊值。因此，Turboshaft 完全依赖 Branch Elimination 的路径敏感条件追踪，而不是类型推断来删除这些检查。

### Turboshaft 中内联的作用

和 Maglev 一样（见上文 *内联对 Hole Check 的作用*），由 TurboFan 执行并输入 Turboshaft 的函数内联会移除闭包边界。一旦内部函数被内联，变量访问和变量定义会成为同一张局部图的一部分。这让 Turboshaft 的强大通用 pass（例如用于常量折叠的 `MachineOptimizationReducer` 和 `BranchEliminationReducer`）可以直接从访问追踪到初始化，从而消除 Parser 和解释器必须保守保留的检查。

## Loop Peeling 和 Unrolling 的影响

在优化编译器（Maglev 和 Turboshaft）中，**Loop Peeling** 和 **Loop Unrolling** 对 hole check elision 很有帮助。

在 baseline 字节码中，循环入口是 merge point：来自循环入口的分析状态和来自 back-edge（循环末尾）的状态必须汇合。这经常迫使编译器保守处理，因为它不能确定前几次迭代产生了什么状态。

通过**剥离循环的第一轮迭代**（把第一轮循环体复制到实际循环头之前）：

1. 第一轮迭代的代码相对于循环入口变成严格线性。
2. 第一轮迭代中发生的任何变量初始化都会直接暴露给图的其余部分，而不需要经过 back-edge merge！
3. 剩余循环迭代中（或循环之后）的后续访问现在可以看到变量已经初始化，从而让编译器安全地消除检查。
