# Generated from Compiscript.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .CompiscriptParser import CompiscriptParser
else:
    from CompiscriptParser import CompiscriptParser

# This class defines a complete listener for a parse tree produced by CompiscriptParser.
class CompiscriptListener(ParseTreeListener):

    # Enter a parse tree produced by CompiscriptParser#program.
    def enterProgram(self, ctx:CompiscriptParser.ProgramContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#program.
    def exitProgram(self, ctx:CompiscriptParser.ProgramContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#statement.
    def enterStatement(self, ctx:CompiscriptParser.StatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#statement.
    def exitStatement(self, ctx:CompiscriptParser.StatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#block.
    def enterBlock(self, ctx:CompiscriptParser.BlockContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#block.
    def exitBlock(self, ctx:CompiscriptParser.BlockContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#variableDeclaration.
    def enterVariableDeclaration(self, ctx:CompiscriptParser.VariableDeclarationContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#variableDeclaration.
    def exitVariableDeclaration(self, ctx:CompiscriptParser.VariableDeclarationContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#constantDeclaration.
    def enterConstantDeclaration(self, ctx:CompiscriptParser.ConstantDeclarationContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#constantDeclaration.
    def exitConstantDeclaration(self, ctx:CompiscriptParser.ConstantDeclarationContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#typeAnnotation.
    def enterTypeAnnotation(self, ctx:CompiscriptParser.TypeAnnotationContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#typeAnnotation.
    def exitTypeAnnotation(self, ctx:CompiscriptParser.TypeAnnotationContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#initializer.
    def enterInitializer(self, ctx:CompiscriptParser.InitializerContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#initializer.
    def exitInitializer(self, ctx:CompiscriptParser.InitializerContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#assignment.
    def enterAssignment(self, ctx:CompiscriptParser.AssignmentContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#assignment.
    def exitAssignment(self, ctx:CompiscriptParser.AssignmentContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#expressionStatement.
    def enterExpressionStatement(self, ctx:CompiscriptParser.ExpressionStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#expressionStatement.
    def exitExpressionStatement(self, ctx:CompiscriptParser.ExpressionStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#printStatement.
    def enterPrintStatement(self, ctx:CompiscriptParser.PrintStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#printStatement.
    def exitPrintStatement(self, ctx:CompiscriptParser.PrintStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#ifStatement.
    def enterIfStatement(self, ctx:CompiscriptParser.IfStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#ifStatement.
    def exitIfStatement(self, ctx:CompiscriptParser.IfStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#whileStatement.
    def enterWhileStatement(self, ctx:CompiscriptParser.WhileStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#whileStatement.
    def exitWhileStatement(self, ctx:CompiscriptParser.WhileStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#doWhileStatement.
    def enterDoWhileStatement(self, ctx:CompiscriptParser.DoWhileStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#doWhileStatement.
    def exitDoWhileStatement(self, ctx:CompiscriptParser.DoWhileStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#forStatement.
    def enterForStatement(self, ctx:CompiscriptParser.ForStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#forStatement.
    def exitForStatement(self, ctx:CompiscriptParser.ForStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#foreachStatement.
    def enterForeachStatement(self, ctx:CompiscriptParser.ForeachStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#foreachStatement.
    def exitForeachStatement(self, ctx:CompiscriptParser.ForeachStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#breakStatement.
    def enterBreakStatement(self, ctx:CompiscriptParser.BreakStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#breakStatement.
    def exitBreakStatement(self, ctx:CompiscriptParser.BreakStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#continueStatement.
    def enterContinueStatement(self, ctx:CompiscriptParser.ContinueStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#continueStatement.
    def exitContinueStatement(self, ctx:CompiscriptParser.ContinueStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#returnStatement.
    def enterReturnStatement(self, ctx:CompiscriptParser.ReturnStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#returnStatement.
    def exitReturnStatement(self, ctx:CompiscriptParser.ReturnStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#tryCatchStatement.
    def enterTryCatchStatement(self, ctx:CompiscriptParser.TryCatchStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#tryCatchStatement.
    def exitTryCatchStatement(self, ctx:CompiscriptParser.TryCatchStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#switchStatement.
    def enterSwitchStatement(self, ctx:CompiscriptParser.SwitchStatementContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#switchStatement.
    def exitSwitchStatement(self, ctx:CompiscriptParser.SwitchStatementContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#switchCase.
    def enterSwitchCase(self, ctx:CompiscriptParser.SwitchCaseContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#switchCase.
    def exitSwitchCase(self, ctx:CompiscriptParser.SwitchCaseContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#defaultCase.
    def enterDefaultCase(self, ctx:CompiscriptParser.DefaultCaseContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#defaultCase.
    def exitDefaultCase(self, ctx:CompiscriptParser.DefaultCaseContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#functionDeclaration.
    def enterFunctionDeclaration(self, ctx:CompiscriptParser.FunctionDeclarationContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#functionDeclaration.
    def exitFunctionDeclaration(self, ctx:CompiscriptParser.FunctionDeclarationContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#parameters.
    def enterParameters(self, ctx:CompiscriptParser.ParametersContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#parameters.
    def exitParameters(self, ctx:CompiscriptParser.ParametersContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#parameter.
    def enterParameter(self, ctx:CompiscriptParser.ParameterContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#parameter.
    def exitParameter(self, ctx:CompiscriptParser.ParameterContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#classDeclaration.
    def enterClassDeclaration(self, ctx:CompiscriptParser.ClassDeclarationContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#classDeclaration.
    def exitClassDeclaration(self, ctx:CompiscriptParser.ClassDeclarationContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#classMember.
    def enterClassMember(self, ctx:CompiscriptParser.ClassMemberContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#classMember.
    def exitClassMember(self, ctx:CompiscriptParser.ClassMemberContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#expression.
    def enterExpression(self, ctx:CompiscriptParser.ExpressionContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#expression.
    def exitExpression(self, ctx:CompiscriptParser.ExpressionContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#AssignExpr.
    def enterAssignExpr(self, ctx:CompiscriptParser.AssignExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#AssignExpr.
    def exitAssignExpr(self, ctx:CompiscriptParser.AssignExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#PropertyAssignExpr.
    def enterPropertyAssignExpr(self, ctx:CompiscriptParser.PropertyAssignExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#PropertyAssignExpr.
    def exitPropertyAssignExpr(self, ctx:CompiscriptParser.PropertyAssignExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#ExprNoAssign.
    def enterExprNoAssign(self, ctx:CompiscriptParser.ExprNoAssignContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#ExprNoAssign.
    def exitExprNoAssign(self, ctx:CompiscriptParser.ExprNoAssignContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#TernaryExpr.
    def enterTernaryExpr(self, ctx:CompiscriptParser.TernaryExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#TernaryExpr.
    def exitTernaryExpr(self, ctx:CompiscriptParser.TernaryExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#logicalOrExpr.
    def enterLogicalOrExpr(self, ctx:CompiscriptParser.LogicalOrExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#logicalOrExpr.
    def exitLogicalOrExpr(self, ctx:CompiscriptParser.LogicalOrExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#logicalAndExpr.
    def enterLogicalAndExpr(self, ctx:CompiscriptParser.LogicalAndExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#logicalAndExpr.
    def exitLogicalAndExpr(self, ctx:CompiscriptParser.LogicalAndExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#equalityExpr.
    def enterEqualityExpr(self, ctx:CompiscriptParser.EqualityExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#equalityExpr.
    def exitEqualityExpr(self, ctx:CompiscriptParser.EqualityExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#relationalExpr.
    def enterRelationalExpr(self, ctx:CompiscriptParser.RelationalExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#relationalExpr.
    def exitRelationalExpr(self, ctx:CompiscriptParser.RelationalExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#additiveExpr.
    def enterAdditiveExpr(self, ctx:CompiscriptParser.AdditiveExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#additiveExpr.
    def exitAdditiveExpr(self, ctx:CompiscriptParser.AdditiveExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#multiplicativeExpr.
    def enterMultiplicativeExpr(self, ctx:CompiscriptParser.MultiplicativeExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#multiplicativeExpr.
    def exitMultiplicativeExpr(self, ctx:CompiscriptParser.MultiplicativeExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#unaryExpr.
    def enterUnaryExpr(self, ctx:CompiscriptParser.UnaryExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#unaryExpr.
    def exitUnaryExpr(self, ctx:CompiscriptParser.UnaryExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#primaryExpr.
    def enterPrimaryExpr(self, ctx:CompiscriptParser.PrimaryExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#primaryExpr.
    def exitPrimaryExpr(self, ctx:CompiscriptParser.PrimaryExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#literalExpr.
    def enterLiteralExpr(self, ctx:CompiscriptParser.LiteralExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#literalExpr.
    def exitLiteralExpr(self, ctx:CompiscriptParser.LiteralExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#leftHandSide.
    def enterLeftHandSide(self, ctx:CompiscriptParser.LeftHandSideContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#leftHandSide.
    def exitLeftHandSide(self, ctx:CompiscriptParser.LeftHandSideContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#IdentifierExpr.
    def enterIdentifierExpr(self, ctx:CompiscriptParser.IdentifierExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#IdentifierExpr.
    def exitIdentifierExpr(self, ctx:CompiscriptParser.IdentifierExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#NewExpr.
    def enterNewExpr(self, ctx:CompiscriptParser.NewExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#NewExpr.
    def exitNewExpr(self, ctx:CompiscriptParser.NewExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#ThisExpr.
    def enterThisExpr(self, ctx:CompiscriptParser.ThisExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#ThisExpr.
    def exitThisExpr(self, ctx:CompiscriptParser.ThisExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#CallExpr.
    def enterCallExpr(self, ctx:CompiscriptParser.CallExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#CallExpr.
    def exitCallExpr(self, ctx:CompiscriptParser.CallExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#IndexExpr.
    def enterIndexExpr(self, ctx:CompiscriptParser.IndexExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#IndexExpr.
    def exitIndexExpr(self, ctx:CompiscriptParser.IndexExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#PropertyAccessExpr.
    def enterPropertyAccessExpr(self, ctx:CompiscriptParser.PropertyAccessExprContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#PropertyAccessExpr.
    def exitPropertyAccessExpr(self, ctx:CompiscriptParser.PropertyAccessExprContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#arguments.
    def enterArguments(self, ctx:CompiscriptParser.ArgumentsContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#arguments.
    def exitArguments(self, ctx:CompiscriptParser.ArgumentsContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#arrayLiteral.
    def enterArrayLiteral(self, ctx:CompiscriptParser.ArrayLiteralContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#arrayLiteral.
    def exitArrayLiteral(self, ctx:CompiscriptParser.ArrayLiteralContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#type.
    def enterType(self, ctx:CompiscriptParser.TypeContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#type.
    def exitType(self, ctx:CompiscriptParser.TypeContext):
        pass


    # Enter a parse tree produced by CompiscriptParser#baseType.
    def enterBaseType(self, ctx:CompiscriptParser.BaseTypeContext):
        pass

    # Exit a parse tree produced by CompiscriptParser#baseType.
    def exitBaseType(self, ctx:CompiscriptParser.BaseTypeContext):
        pass



del CompiscriptParser