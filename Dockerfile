FROM public.ecr.aws/lambda/python:3.12

# Install browser dependencies
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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers in the Lambda task root so they persist
ENV PLAYWRIGHT_BROWSERS_PATH=${LAMBDA_TASK_ROOT}/playwright-browsers
RUN playwright install chromium

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}

# Set the handler
CMD ["lambda_handler.lambda_handler"]