// @caso: == != < <= > >= sobre enteros y strings; salto fusionado `if a op b goto`
// @salida: true | true | false | false | true | false | true | true | en rango
// @contiene: if @x < 5 goto
// @contiene: if @x >= 10 goto
print(1 < 2);
print(2 <= 2);
print(3 > 4);
print(4 >= 5);
print(1 == 1);
print(1 != 1);
print("a" == "a");
print("a" != "b");
let x: integer = 5;
if (x >= 5 && x < 10) { print("en rango"); }
