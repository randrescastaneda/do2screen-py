* Mutual dependency: a depends on b, b depends on a. Must terminate.
gen a = b + 1
gen b = a + 1
gen c = a + b