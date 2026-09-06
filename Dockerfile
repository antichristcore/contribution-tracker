FROM alpine:3.23

WORKDIR /usr/local/app
RUN apk update
COPY . .

# Create DB
RUN mkdir data
RUN touch data/app.db

# Backend build
RUN apk add --no-cache "python3<3.13" "python3-dev<3.13" py3-pip build-base
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages --index-url https://pypi-mirror.gitverse.ru/simple/ # Mirror
RUN pip install --no-cache-dir -r requirements-dev.txt --break-system-packages --index-url https://pypi-mirror.gitverse.ru/simple/ # Mirror

# Frontend build
RUN apk add --no-cache npm typescript
RUN npm config set registry https://npm-mirror.gitverse.ru # Mirror
RUN npm install --prefix ./frontend
RUN npm run build --prefix ./frontend --include=dev


# Tests 0/1
ARG RUN_TESTS=1
RUN if ["$RUN_TESTS" = "1"]; then pytest -x tests; echo "Tests passed"; fi

# Clean
RUN pip uninstall -r requirements-dev.txt --break-system-packages -y
RUN apk del py3-pip build-base python3-dev

# Open port
ENV APP_PORT=8000
EXPOSE $APP_PORT

# Entry
CMD ["sh", "-c", "python -m uvicorn backend.app.main:app --port \"$APP_PORT\" --host 0.0.0.0"]
