# A minimal study of list summation in Python

## Abstract
We compare three methods of summing a list of integers: a for-loop,
the built-in `sum`, and NumPy's `np.sum`. Benchmarks on lists of
length 10^3 to 10^6 show `np.sum` wins for N > 10^4.

## Methods
Each method run 10 times per N; mean wall-clock time recorded on a
single laptop (M1, 16GB).

## Results
| N         | for-loop  | sum     | np.sum  |
|-----------|-----------|---------|---------|
| 1,000     | 0.05 ms   | 0.01 ms | 0.03 ms |
| 1,000,000 | 45.0 ms   | 8.5 ms  | 0.9 ms  |

## Conclusion
For large N use NumPy; for small N `sum` is fastest.
