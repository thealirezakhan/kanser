FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# ponytail: npm install not ci - lock generated on Windows misses linux-only
# optional platform entries (@emnapi); regenerate lock from linux CI when that matters
RUN npm install

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
