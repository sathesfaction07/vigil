#!/usr/bin/env bash
set -e

VENV_DIR=".venv"
PYTHON_MIN="3.11"

detect_os() {
    case "$(uname -s)" in
        Linux*)   OS="linux" ;;
        Darwin*)  OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)        OS="unknown" ;;
    esac
    echo "Detected OS: $OS"
}

find_python() {
    for cmd in python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            PYTHON="$cmd"
            echo "Using Python: $PYTHON"
            return 0
        fi
    done
    echo "ERROR: Python >= $PYTHON_MIN not found."
    exit 1
}

setup_venv() {
    if [ -d "$VENV_DIR" ]; then
        echo "Virtual environment exists — reusing."
    else
        $PYTHON -m venv "$VENV_DIR"
    fi

    if [ "$OS" = "windows" ]; then source "$VENV_DIR/Scripts/activate"; else source "$VENV_DIR/bin/activate"; fi
    pip install --upgrade pip --quiet
    pip install -e ".[dev]" --quiet
    echo "Dependencies installed."
}

select_cloud_provider() {
    echo ""
    echo "  ContentGuard requires AWS Bedrock (Claude) for classification"
    echo "  and Redis for job queuing."
    echo ""
    echo "  1) Configure AWS (Bedrock access + optional Comprehend)"
    echo "  2) Skip cloud setup (configure manually later)"
    echo ""
    read -p "Selection [1/2]: " CHOICE

    case "$CHOICE" in
        1) setup_aws ;;
        *) echo "Skipping. Set CG_BEDROCK_REGION and AWS credentials manually." ;;
    esac
}

setup_aws() {
    read -p "AWS Account ID: " AWS_ACCOUNT_ID
    read -p "AWS Region [us-east-1]: " AWS_REGION
    AWS_REGION=${AWS_REGION:-us-east-1}

    ROLE_NAME="ContentGuard-AppRole"
    POLICY_NAME="ContentGuard-BedrockAccess"

    TRUST_POLICY="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"AWS\":\"arn:aws:iam::${AWS_ACCOUNT_ID}:root\"},\"Action\":\"sts:AssumeRole\"}]}"

    ACCESS_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/*"
        },
        {
            "Effect": "Allow",
            "Action": ["comprehend:DetectEntities", "comprehend:DetectDominantLanguage"],
            "Resource": "*"
        }
    ]
}
EOF
)

    if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null 2>&1; then
        echo "Role $ROLE_NAME exists — skipping creation."
    else
        aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "$TRUST_POLICY" --output text --query 'Role.Arn'
        echo "Created role: $ROLE_NAME"
    fi

    aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" --policy-document "$ACCESS_POLICY" 2>/dev/null
    echo "Attached Bedrock + Comprehend policy."

    cat > .env <<EOF
CG_BEDROCK_REGION=${AWS_REGION}
CG_ENRICHER=comprehend
EOF
    echo "Configuration written to .env"
}

check_redis() {
    if command -v redis-cli &>/dev/null && redis-cli ping &>/dev/null 2>&1; then
        echo "Redis is running."
    else
        echo ""
        echo "  WARNING: Redis is not running."
        echo "  ContentGuard needs Redis for job queuing."
        echo "  Start with: redis-server &"
        echo "  Or use: docker compose up (includes Redis)"
    fi
}

run_app() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Starting ContentGuard..."
    echo "  API:      http://localhost:5050"
    echo "  Frontend: http://localhost:3000"
    echo "═══════════════════════════════════════════════════════════════"

    [ -f .env ] && export $(grep -v '^#' .env | xargs)

    python3 -m http.server 3000 --directory frontend &>/dev/null &
    echo "Frontend: http://localhost:3000"

    python -m content_guard.queue.worker &
    echo "Worker started."

    python -m content_guard.api.app
}

main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║            ContentGuard — Setup & Run                        ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
    detect_os
    find_python
    setup_venv
    select_cloud_provider
    check_redis
    run_app
}

main "$@"
