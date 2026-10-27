grammar Compiscript;

// ------------------
// Parser Rules
// ------------------

program: statement* EOF;

statement
  : variableDeclaration
  | constantDeclaration
  | assignment
  | functionDeclaration
  | classDeclaration
  | expressionStatement
  | printStatement
  | block
  | ifStatement
  | whileStatement
  | doWhileStatement
  | forStatement
  | foreachStatement
  | tryCatchStatement
  | switchStatement
  | breakStatement
  | continueStatement
  | returnStatement
  ;

block: '{' statement* '}';

variableDeclaration
  : ('let' | 'var') Identifier typeAnnotation? initializer? ';'
  ;

constantDeclaration
  : 'const' Identifier typeAnnotation? '=' expression ';'
  ;

typeAnnotation: ':' type;
initializer: '=' expression;

assignment
  : Identifier '=' expression ';'
  | expression '.' Identifier '=' expression ';' // property assignment
  ;

expressionStatement: expression ';';
printStatement: 'print' '(' expression ')' ';';

ifStatement: 'if' '(' expression ')' block ('else' block)?;
whileStatement: 'while' '(' expression ')' block;
doWhileStatement: 'do' block 'while' '(' expression ')' ';';
forStatement: 'for' '(' (variableDeclaration | assignment | ';') expression? ';' expression? ')' block;
foreachStatement: 'foreach' '(' Identifier 'in' expression ')' block;
breakStatement: 'break' ';';
continueStatement: 'continue' ';';
returnStatement: 'return' expression? ';';

tryCatchStatement: 'try' block 'catch' '(' Identifier ')' block;

switchStatement: 'switch' '(' expression ')' '{' switchCase* defaultCase? '}';
switchCase: 'case' expression ':' statement*;
defaultCase: 'default' ':' statement*;

functionDeclaration: 'function' Identifier '(' parameters? ')' (':' type)? block;
parameters: parameter (',' parameter)*;
parameter: Identifier (':' type)?;

classDeclaration: 'class' Identifier (':' Identifier)? '{' classMember* '}';
classMember: functionDeclaration | variableDeclaration | constantDeclaration;

// ------------------
// Expression Rules — Operator Precedence
// ------------------

expression: assignmentExpr;

assignmentExpr
  : lhs=leftHandSide '=' assignmentExpr            # AssignExpr
  | lhs=leftHandSide '.' Identifier '=' assignmentExpr # PropertyAssignExpr
  | conditionalExpr                                # ExprNoAssign
  ;

conditionalExpr
  : logicalOrExpr ('?' expression ':' expression)? # TernaryExpr
  ;

logicalOrExpr
  : logicalAndExpr ( '||' logicalAndExpr )*
  ;

logicalAndExpr
  : equalityExpr ( '&&' equalityExpr )*
  ;

equalityExpr
  : relationalExpr ( ('==' | '!=') relationalExpr )*
  ;

relationalExpr
  : additiveExpr ( ('<' | '<=' | '>' | '>=') additiveExpr )*
  ;

additiveExpr
  : multiplicativeExpr ( ('+' | '-') multiplicativeExpr )*
  ;

multiplicativeExpr
  : unaryExpr ( ('*' | '/' | '%') unaryExpr )*
  ;

unaryExpr
  : ('-' | '!') unaryExpr
  | primaryExpr
  ;

primaryExpr
  : literalExpr
  | leftHandSide
  | '(' expression ')'
  ;

literalExpr
  : Literal
  | arrayLiteral
  | 'null'
  | 'true'
  | 'false'
  ;

leftHandSide
  : primaryAtom (suffixOp)*
  ;

primaryAtom
  : Identifier                                 # IdentifierExpr
  | 'new' Identifier '(' arguments? ')'        # NewExpr
  | 'this'                                     # ThisExpr
  ;

suffixOp
  : '(' arguments? ')'                        # CallExpr
  | '[' expression ']'                        # IndexExpr
  | '.' Identifier                            # PropertyAccessExpr
  ;

arguments: expression (',' expression)*;

arrayLiteral: '[' (expression (',' expression)*)? ']';

// ------------------
// Types
// ------------------

type: baseType ('[' ']')*;
baseType: 'boolean' | 'integer' | 'float' | 'string' | Identifier;

// ------------------
// Lexer Rules
// ------------------

Literal
  : IntegerLiteral
  | FloatLiteral
  | StringLiteral
  ;

IntegerLiteral: [0-9]+;
FloatLiteral: [0-9]+ '.' [0-9]+;
// admite secuencias de escape: \" \\ \n \t ...
StringLiteral: '"' (~["\\\r\n] | '\\' .)* '"';

Identifier: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\r\n]+ -> skip;
COMMENT: '//' ~[\r\n]* -> skip;
MULTILINE_COMMENT: '/*' .*? '*/' -> skip;
