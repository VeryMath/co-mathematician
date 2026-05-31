# 计算实验：PDHG vs Douglas-Rachford 数值对比

## 1. 实验设计

在三个经典连续优化问题上对比 PDHG 和 DRS 的数值性能：

| 问题 | 规模 | 正则化 | PDHG 优势 | DRS 优势 |
|------|------|--------|-----------|----------|
| LASSO | 500×200 | L1 | $\text{prox}_{f^*}$ = $\ell_\infty$ 投影 (闭式) | — |
| TV 去噪 | 128 | 全变差 | $\text{prox}_{f^*}$ = box 投影 (闭式) | — |
| 矩阵补全 | 50×50 | 核范数 | $\text{prox}_{f^*}$ = 谱范数投影 | — |

**硬件**: Apple Silicon (M-series), Python 3.13 + NumPy

## 2. 结果

### 2.1 LASSO

min_x 0.5||Ax - b||^2 + λ||x||_1, λ=0.1

| 指标 | PDHG | DRS |
|------|------|-----|
| 最终残差 | 5.74×10⁻¹⁷ | 1.96×10⁻⁵ |
| 运行时间 | 0.114s | 1.317s |
| 每步主运算 | prox (O(p)) + matvec | 线性方程组求解 (O(p³)) |

**分析**: PDHG 大幅领先。根本原因：LASSO 的 $f(x) = 0.5\|Ax-b\|^2$ 的 prox 需要求解 (AᵀA + I/γ) 线性系统 ($O(p^3)$)，而 $f^*$ 的 prox 是简单的 affine 变换 ($O(np)$)。这是 $\text{prox}_{f^*}$ 比 $\text{prox}_f$ 容易的典型案例。

### 2.2 TV Denoising

min_x 0.5||x - y||^2 + λ||Dx||_1, λ=0.5

| 指标 | PDHG | DRS |
|------|------|-----|
| 最终残差 | 1.02×10⁻⁹ | 5.09×10⁻¹⁶ |
| 运行时间 | 0.039s | 0.955s |
| 每步主运算 | 软阈值 $O(n)$ + matvec | **内层 50 步 PDHG** sub-iteration |

**分析**: PDHG 速度优势约 25×。根本原因：DRS 的 $\text{prox}_f$ (TV 正则化) 需要内层优化求解，而 PDHG 的 $\text{prox}_{f^*}$ (box 投影) 是 $O(n)$ 闭式解。这验证了理论分析中的关键判断 #1。

### 2.3 Matrix Completion

min_X 0.5||P_Ω(X - Y)||² + λ||X||_*, λ=1.0

| 指标 | PDHG | DRS |
|------|------|-----|
| 最终残差 | 4.50×10⁻⁴ | 7.59×10⁻⁴ |
| 运行时间 | 0.287s | 0.329s |
| 每步主运算 | SVD $O(mn\cdot r)$ | SVD $O(mn\cdot r)$ |

**分析**: 两者性能接近。PDHG 的 $\text{prox}_{f^*}$ (投影到谱范数球) 和 DRS 的 $\text{prox}_f$ (核范数阈值) 都需要 SVD，计算代价相同。PDHG 略快是由于免去了 DRS 的松弛步骤中的额外矩阵运算。

## 3. 综合讨论

### 3.1 实验结果与理论预测的一致性

| 理论判据 | LASSO | TV 去噪 | 矩阵补全 |
|----------|-------|---------|----------|
| $\text{prox}_{f^*}$ 是否闭式 | ✓ (affine) | ✓ (projection) | ✗ (SVD) |
| PDHG 理论优势 | 强 | 很强 | 弱 |
| 实验结果 | PDHG 11× faster | PDHG 24× faster | 几乎相同 |

→ 实验结果与 G2 理论分析中的 **Prox 代价比判据** 高度一致。

### 3.2 关键发现

1. **PDHG 的优势集中在 $\text{prox}_{f^*}$ 容易计算的问题上**。LASSO 和 TV 去噪是典型代表。
2. **当两种 prox 都需要相同计算时，两者性能接近**（如矩阵补全）。
3. **DRS 在 TV 问题上的内层迭代代价使其不适用** — 这个观察强化了 G2 中的建议：若 $\text{prox}_f$ 需要内层优化而 $\text{prox}_{f^*}$ 是闭式，PDHG 是明确最优选择。
4. **DRS 的最终残差有时更低**（TV 5e-16 vs PDHG 1e-09），但以 ≈25× 的时间代价获得。
5. **LASSO 中 DRS 的线性系统求解成为瓶颈**（1.32s vs 0.11s），即使问题只有 200 维。

### 3.3 局限性

- 所有实验使用固定步长，未测试自适应/免调参变体
- 矩阵补全问题规模较小 (50×50)，大尺度下的差异可能更显著
- 未测试 $\|A\|$ 较大时的 PDHG 退化（理论预测 DRS 更优）
- 代码为教学目的编写，未优化 BLAS/LAPACK 调用

## 4. 可重现性

实验代码: `artifacts/compare_pdhg_drs.py`
原始数据: `artifacts/results.json`

运行:
```bash
python3 artifacts/compare_pdhg_drs.py
```

## 来源

- Chambolle & Pock (2011): JMIV 40, 120-145
- Chambolle & Pock (2016): Acta Numerica 25, 161-319
- O'Connor & Vandenberghe (2020): Math. Prog. 179, 85-108
