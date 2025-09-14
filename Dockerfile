FROM public.ecr.aws/lambda/python:3.12-arm64

# Install uv for dependency management
RUN pip install uv

# Install browser dependencies required for Playwright
RUN dnf install -y \
    alsa-lib \
    at-spi2-atk \
    atk \
    cairo \
    cairo-gobject \
    cups-libs \
    dbus-glib \
    fontconfig \
    gdk-pixbuf2 \
    glib2 \
    gtk3 \
    libX11 \
    libXcomposite \
    libXdamage \
    libXext \
    libXfixes \
    libXrandr \
    libXtst \
    libdrm \
    libxcb \
    libxkbcommon \
    mesa-libgbm \
    nss \
    pango \
    && dnf clean all

# Copy dependency files and README for better caching
COPY pyproject.toml uv.lock README.md ./

# Install Python dependencies using uv, creating the virtual environment in-place
ENV UV_PROJECT_ENVIRONMENT=${LAMBDA_TASK_ROOT}/.venv
RUN uv sync --frozen

# Add the virtual environment to Python path
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/.venv/lib/python3.12/site-packages:${PYTHONPATH}"

# Install Playwright browsers in the Lambda task root
ENV PLAYWRIGHT_BROWSERS_PATH=${LAMBDA_TASK_ROOT}/playwright-browsers
RUN ${LAMBDA_TASK_ROOT}/.venv/bin/playwright install chromium

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}

# Set the handler
CMD ["lambda_handler.lambda_handler"]