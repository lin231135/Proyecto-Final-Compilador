// @caso: R9 mismo nombre en ambitos distintos (shadowing) esta permitido
let x: integer = 1;
{
  let x: integer = 2;
  print(x);
}
