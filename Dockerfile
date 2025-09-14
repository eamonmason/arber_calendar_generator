FROM public.ecr.aws/lambda/python:3.12

# Install uv for dependency management
RUN pip install uv

# Install Node.js for x86_64 (required for Playwright)
RUN dnf install -y nodejs npm && dnf clean all

# Install browser dependencies for Playwright on Amazon Linux
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
    xorg-x11-fonts-75dpi \
    xorg-x11-fonts-100dpi \
    xorg-x11-fonts-Type1 \
    xorg-x11-utils \
    && dnf clean all

# Copy dependency files and README for better caching
COPY pyproject.toml uv.lock README.md ./

# Install Python dependencies using uv, creating the virtual environment in-place
ENV UV_PROJECT_ENVIRONMENT=${LAMBDA_TASK_ROOT}/.venv
RUN uv sync --frozen

# Add the virtual environment to Python path
ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/.venv/lib/python3.12/site-packages:${PYTHONPATH}"

# Set environment variables for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=${LAMBDA_TASK_ROOT}/playwright-browsers
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true

# Install Playwright browsers
RUN ${LAMBDA_TASK_ROOT}/.venv/bin/playwright install chromium

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}

# Set the handler
CMD ["lambda_handler.lambda_handler"]