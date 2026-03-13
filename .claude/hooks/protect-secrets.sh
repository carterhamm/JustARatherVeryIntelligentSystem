#!/bin/bash
# Prevent Claude from editing files that contain secrets or credentials.
# Used as a PreToolUse hook for Edit and Write tools.

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Block editing sensitive files
case "$BASENAME" in
  .env|.env.local|.env.production|.env.development)
    echo "BLOCKED: Cannot edit $BASENAME — contains secrets. Use 'railway variables --set' instead." >&2
    exit 2
    ;;
  credentials.json|service-account.json|*.pem|*.key)
    echo "BLOCKED: Cannot edit $BASENAME — contains credentials." >&2
    exit 2
    ;;
esac

exit 0
