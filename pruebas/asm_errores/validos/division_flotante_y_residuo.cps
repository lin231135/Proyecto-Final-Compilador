// @caso: la division y el residuo entre cero se detectan tambien en float y en %
// @salida: division entre cero | division entre cero | division entre cero
let z: float = 0.0;
let n: integer = 0;
try { print(1.5 / z); } catch (e) { print(e); }
try { print(1.5 % z); } catch (e) { print(e); }
try { print(5 % n); } catch (e) { print(e); }
