def is_valid_parentheses(text: str) -> bool:
    balance = 0
    for char in text:
        if char == '(':
            balance += 1
        elif char == ')':
            if balance == 0:
                return False
            balance -= 1
    return balance == 0
