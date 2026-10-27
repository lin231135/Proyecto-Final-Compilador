// @caso: una funcion lee y escribe variables globales (area estatica)
// @salida: 7
// @contiene: @total = @total + 
let total: integer = 0;
function suma(n: integer) { total = total + n; }
suma(3);
suma(4);
print(total);
