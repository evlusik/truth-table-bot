import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import itertools
import io
import csv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Состояния для ConversationHandler
WAITING_EXPRESSION = 1

class TruthTableBot:
    def __init__(self):
        self.allowed_operators = {'&', '|', '!', '→', '↔', '(', ')', ' ', '\t', '\n'}

    def validate_expression(self, expression: str) -> tuple:
        if not expression or expression.isspace():
            return False, "Выражение не может быть пустым!", []
        
        # Проверка скобок
        stack = []
        for char in expression:
            if char == '(':
                stack.append(char)
            elif char == ')':
                if not stack:
                    return False, "Несбалансированные скобки!", []
                stack.pop()
        
        if stack:
            return False, "Несбалансированные скобки!", []
        
        # Извлечение переменных
        variables = set()
        i = 0
        while i < len(expression):
            char = expression[i]
            
            if char.isspace():
                i += 1
                continue
            
            if char in self.allowed_operators:
                i += 1
                continue
            
            if char.isalpha() or char.isdigit():
                var_name = ""
                while i < len(expression) and (expression[i].isalnum() or expression[i] == '_'):
                    var_name += expression[i]
                    i += 1
                
                forbidden_vars = {'V', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'X'}
                if var_name in forbidden_vars:
                    return False, f"Использование переменной '{var_name}' запрещено!", []
                
                variables.add(var_name)
                continue
            
            return False, f"Недопустимый символ: '{char}'", []
        
        if not variables:
            return False, "В выражении должны быть переменные!", []
        
        return True, "", sorted(list(variables))
    
    def evaluate_expression(self, expression: str, variables: dict) -> bool:
        expr = expression.replace('&', ' and ')
        expr = expr.replace('|', ' or ')
        expr = expr.replace('!', ' not ')
        expr = expr.replace('→', ' <= ')
        expr = expr.replace('↔', ' == ')
        
        for var, value in variables.items():
            expr = expr.replace(var, str(value))
        
        try:
            result = eval(expr)
            return bool(result)
        except:
            return False
    
    def build_truth_table(self, expression: str, variables: list) -> dict:
        n = len(variables)
        results = []
        true_count = 0
        false_count = 0
        
        for values in itertools.product([False, True], repeat=n):
            var_dict = dict(zip(variables, values))
            result = self.evaluate_expression(expression, var_dict)
            
            row = list(values) + [result]
            results.append(row)
            
            if result:
                true_count += 1
            else:
                false_count += 1
        
        return {
            'headers': variables + ['Result'],
            'rows': results,
            'true_count': true_count,
            'false_count': false_count,
            'total': len(results)
        }
    
    def format_table_text(self, expression: str, table_data: dict) -> str:
        headers = table_data['headers']
        rows = table_data['rows']
        
        col_widths = [max(len(str(h)), 2) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(int(val))))
        
        table_lines = []
        
        header_line = "|"
        separator_line = "|"
        for i, header in enumerate(headers):
            header_line += f" {header:^{col_widths[i]}} |"
            separator_line += "-" * (col_widths[i] + 2) + "|"
        
        table_lines.append(header_line)
        table_lines.append(separator_line)
        
        for row in rows:
            row_line = "|"
            for i, val in enumerate(row):
                display_val = "1" if val else "0"
                row_line += f" {display_val:^{col_widths[i]}} |"
            table_lines.append(row_line)
        
        table_text = "\n".join(table_lines)
        
        summary = f"""
📊 Итоги для выражения: {expression}
• Выражение истинно в {table_data['true_count']} случаях из {table_data['total']}
• Выражение ложно в {table_data['false_count']} случаях из {table_data['total']}
"""
        
        return table_text + summary
    
    def create_text_file(self, expression: str, table_data: dict) -> io.BytesIO:
        text_content = f"Таблица истинности для выражения: {expression}\n\n"
        text_content += self.format_table_text(expression, table_data)
        
        file_buffer = io.BytesIO(text_content.encode('utf-8'))
        file_buffer.seek(0)
        return file_buffer
    
    def create_csv_file(self, expression: str, table_data: dict) -> io.BytesIO:
        file_buffer = io.StringIO()
        writer = csv.writer(file_buffer, delimiter=',', lineterminator='\n', quoting=csv.QUOTE_MINIMAL)
        
        writer.writerow(table_data['headers'])
        for row in table_data['rows']:
            writer.writerow([int(val) for val in row])
        
        csv_buffer = io.BytesIO(file_buffer.getvalue().encode('utf-8-sig'))
        csv_buffer.seek(0)
        return csv_buffer

bot = TruthTableBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    welcome_text = """
🔍 Добро пожаловать в LogicTableBot!

Я помогу построить таблицу истинности для логического выражения.

📋 Доступные символы:
• & (И), | (ИЛИ), ! (НЕ), → (импликация), ↔ (эквивалентность)
• Скобки: ( )
• Переменные: латинские буквы (кроме V,A,B,C,D,E,F,G,H,X) и цифры

📌 Примеры: a & b, !(a | b) → c, (p → q) & !r

Введите ваше логическое выражение:
"""
    await update.message.reply_text(welcome_text, reply_markup=ReplyKeyboardRemove())
    return WAITING_EXPRESSION

async def handle_expression(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_expression = update.message.text.strip()
    
    is_valid, error_msg, variables = bot.validate_expression(user_expression)
    
    if not is_valid:
        await update.message.reply_text(f"❌ Ошибка!\n{error_msg}\n\nПожалуйста, введите выражение еще раз:")
        return WAITING_EXPRESSION
    
    table_data = bot.build_truth_table(user_expression, variables)
    table_text = bot.format_table_text(user_expression, table_data)
    
    if len(table_text) > 4000:
        parts = [table_text[i:i+4000] for i in range(0, len(table_text), 4000)]
        for part in parts:
            await update.message.reply_text(f"```\n{part}\n```", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(f"```\n{table_text}\n```", parse_mode='MarkdownV2')
    
    keyboard = [["📁 Скачать TXT", "📊 Скачать CSV"], ["🔄 Новое выражение"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text("Выберите формат для скачивания или введите новое выражение:", reply_markup=reply_markup)
    
    context.user_data['last_expression'] = user_expression
    context.user_data['last_table_data'] = table_data
    
    return WAITING_EXPRESSION

async def handle_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_choice = update.message.text
    user_data = context.user_data
    
    if 'last_expression' not in user_data or 'last_table_data' not in user_data:
        await update.message.reply_text("❌ Нет данных для скачивания. Введите выражение сначала.", reply_markup=ReplyKeyboardRemove())
        return WAITING_EXPRESSION
    
    expression = user_data['last_expression']
    table_data = user_data['last_table_data']
    
    try:
        if user_choice == "📁 Скачать TXT":
            file_buffer = bot.create_text_file(expression, table_data)
            filename = f"truth_table.txt"
        elif user_choice == "📊 Скачать CSV":
            file_buffer = bot.create_csv_file(expression, table_data)
            filename = f"truth_table.csv"
        
        await update.message.reply_document(document=file_buffer, filename=filename, caption=f"Таблица истинности для: {expression}")
        await update.message.reply_text("Файл отправлен! Введите новое выражение или выберите действие:")
        
    except Exception as e:
        await update.message.reply_text("❌ Ошибка при создании файла. Попробуйте еще раз.", reply_markup=ReplyKeyboardRemove())
    
    return WAITING_EXPRESSION

async def handle_new_expression(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите ваше новое логическое выражение:", reply_markup=ReplyKeyboardRemove())
    return WAITING_EXPRESSION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена. Используйте /start чтобы начать заново.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    TOKEN = "8292449792:AAHCKCNLhxAtYIEOJ4txw4TM-eQVO13R0cY"
    
    if not TOKEN:
        print("ERROR: TOKEN не установлен")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_EXPRESSION: [
                MessageHandler(filters.Regex('^(📁 Скачать TXT|📊 Скачать CSV)$'), handle_download),
                MessageHandler(filters.Regex('^🔄 Новое выражение$'), handle_new_expression),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_expression)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    print("Бот запускается...")
    application.run_polling()

if __name__ == '__main__':
    main()