FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000

# Dev server: the dashboard is a thin client over the API, and hot reload is
# more useful here than a production build. For production, run
# `npm run build && npm run start` instead.
CMD ["npm", "run", "dev"]
