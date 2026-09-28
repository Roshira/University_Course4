-- ІС "Індивідуальна робота кафедри зі студентами" — структура БД (MySQL 8)
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS individual_work
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE individual_work;

DROP TABLE IF EXISTS answers;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS materials;
DROP TABLE IF EXISTS assignments;
DROP TABLE IF EXISTS schedule;
DROP TABLE IF EXISTS topics;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS teachers;

-- 1. Викладачі
CREATE TABLE teachers (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(150) NOT NULL,
  position  ENUM('Асистент','Старший викладач','Доцент','Професор','Завідувач кафедри') NOT NULL,
  degree    VARCHAR(100) NULL,
  email     VARCHAR(120) NULL,
  phone     VARCHAR(30)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Студенти
CREATE TABLE students (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  full_name  VARCHAR(150) NOT NULL,
  group_name VARCHAR(20)  NOT NULL,
  course     TINYINT      NOT NULL,
  email      VARCHAR(120) NULL,
  phone      VARCHAR(30)  NULL,
  CHECK (course BETWEEN 1 AND 6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Теми індивідуальної роботи (керівник + студент + терміни)
CREATE TABLE topics (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  title       VARCHAR(255) NOT NULL,
  description TEXT NULL,
  teacher_id  INT NOT NULL,
  student_id  INT NOT NULL,
  start_date  DATE NOT NULL,
  end_date    DATE NOT NULL,
  status      ENUM('Заплановано','В роботі','Завершено','Скасовано') NOT NULL DEFAULT 'Заплановано',
  CONSTRAINT fk_topic_teacher FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT,
  CONSTRAINT fk_topic_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Графік роботи
CREATE TABLE schedule (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  topic_id     INT NOT NULL,
  meeting_date DATE NOT NULL,
  start_time   TIME NOT NULL,
  end_time     TIME NOT NULL,
  room         VARCHAR(150) NULL,
  kind         ENUM('Консультація','Перевірка завдання','Захист','Онлайн-зустріч') NOT NULL,
  note         TEXT NULL,
  CONSTRAINT fk_schedule_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Завдання та їх виконання
CREATE TABLE assignments (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  topic_id        INT NOT NULL,
  title           VARCHAR(255) NOT NULL,
  description     TEXT NULL,
  deadline        DATE NOT NULL,
  status          ENUM('Видано','В процесі','Здано','На доопрацюванні','Зараховано') NOT NULL DEFAULT 'Видано',
  submitted_on    DATE NULL,
  grade           TINYINT NULL,
  teacher_comment TEXT NULL,
  CONSTRAINT fk_assignment_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE,
  CHECK (grade IS NULL OR grade BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Допоміжні інформаційні матеріали до тем
CREATE TABLE materials (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  topic_id      INT NOT NULL,
  title         VARCHAR(255) NOT NULL,
  material_type ENUM('Література','Стаття','Методичка','Відео','Презентація','Приклад коду','Інше') NOT NULL,
  url           VARCHAR(500) NULL,
  description   TEXT NULL,
  CONSTRAINT fk_material_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Питання студентів
CREATE TABLE questions (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  student_id    INT NOT NULL,
  teacher_id    INT NOT NULL,
  topic_id      INT NULL,
  question_text TEXT NOT NULL,
  asked_at      DATETIME NOT NULL,
  CONSTRAINT fk_question_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
  CONSTRAINT fk_question_teacher FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT,
  CONSTRAINT fk_question_topic   FOREIGN KEY (topic_id)   REFERENCES topics(id)   ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Відповіді викладачів
CREATE TABLE answers (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  question_id INT NOT NULL,
  teacher_id  INT NOT NULL,
  answer_text TEXT NOT NULL,
  answered_at DATETIME NOT NULL,
  CONSTRAINT fk_answer_question FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
  CONSTRAINT fk_answer_teacher  FOREIGN KEY (teacher_id)  REFERENCES teachers(id)  ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Користувач для програми
CREATE USER IF NOT EXISTS 'lab1'@'localhost' IDENTIFIED WITH mysql_native_password BY 'lab1pass';
CREATE USER IF NOT EXISTS 'lab1'@'%'         IDENTIFIED WITH mysql_native_password BY 'lab1pass';
GRANT ALL PRIVILEGES ON individual_work.* TO 'lab1'@'localhost';
GRANT ALL PRIVILEGES ON individual_work.* TO 'lab1'@'%';
FLUSH PRIVILEGES;
