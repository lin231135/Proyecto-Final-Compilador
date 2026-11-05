// @caso: desbordamiento de 32 bits, division truncada y residuo con signo del dividendo
// @salida: -2147483648 | -3 | -1 | 1 | 0 | 1410065408 | -2147483648 | 3
// @mips: mflo
// @mips: mfhi
// @arm: sdiv
// @arm: msub
print(2147483647 + 1);
print(-7 / 2);
print(-7 % 2);
print(7 % -2);
print(65536 * 65536);
print(100000 * 100000);
print(-2147483647 - 1);
print(7 / 2);
