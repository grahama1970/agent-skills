def remove_invalid_parentheses(text: str) -> str:
    chars = list(text)
    stack: list[int] = []
    for index, char in enumerate(chars):
        if char == '(':
            stack.append(index)
        elif char == ')' and stack:
            stack.pop()
        elif char == ')':
            chars[index] = ''
    while stack:
        chars[stack.pop()] = ''
    return ''.join(chars)
