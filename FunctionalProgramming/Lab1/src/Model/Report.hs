{-# LANGUAGE ExistentialQuantification #-}
{-# LANGUAGE OverloadedStrings         #-}
-- | Звіти (аналітичні запити) як екземпляри класу 'Report'.
module Model.Report
  ( Report (..)
  , SomeReport (..)
  , allReports
  , findReport
  , StudentProgress (..)
  , OverdueAssignments (..)
  , OpenQuestions (..)
  , UpcomingMeetings (..)
  , TeacherLoad (..)
  ) where

import           Data.List           (find)
import           Data.Text           (Text)
import           Database.MySQL.Base (MySQLValue)

import           Model.Field         (valueText)

class Report r where
  reportSlug        :: r -> Text
  reportTitle       :: r -> Text
  reportDescription :: r -> Text
  reportHeaders     :: r -> [Text]
  reportSql         :: r -> Text
  -- | Необов'язкове посилання-дія для рядка звіту: (підпис, URL).
  rowAction         :: r -> [MySQLValue] -> Maybe (Text, Text)
  rowAction _ _ = Nothing

data SomeReport = forall r. Report r => SomeReport r

data StudentProgress    = StudentProgress
data OverdueAssignments = OverdueAssignments
data OpenQuestions      = OpenQuestions
data UpcomingMeetings   = UpcomingMeetings
data TeacherLoad        = TeacherLoad

instance Report StudentProgress where
  reportSlug _        = "progress"
  reportTitle _       = "Успішність студентів"
  reportDescription _ = "Кількість тем і завдань кожного студента, зараховані завдання та середня оцінка."
  reportHeaders _     = ["Студент", "Група", "Тем", "Завдань", "Зараховано", "Прострочено", "Середня оцінка"]
  reportSql _ =
    "SELECT s.full_name, s.group_name, \
    \  COUNT(DISTINCT tp.id), COUNT(a.id), \
    \  CAST(COALESCE(SUM(a.status = 'Зараховано'), 0) AS SIGNED), \
    \  CAST(COALESCE(SUM(a.deadline < CURDATE() AND a.status NOT IN ('Здано','Зараховано')), 0) AS SIGNED), \
    \  CAST(ROUND(AVG(a.grade), 1) AS CHAR) \
    \FROM students s \
    \LEFT JOIN topics tp ON tp.student_id = s.id \
    \LEFT JOIN assignments a ON a.topic_id = tp.id \
    \GROUP BY s.id, s.full_name, s.group_name \
    \ORDER BY s.full_name"

instance Report OverdueAssignments where
  reportSlug _        = "overdue"
  reportTitle _       = "Прострочені завдання"
  reportDescription _ = "Завдання, термін яких минув, але вони ще не здані."
  reportHeaders _     = ["id", "Студент", "Тема", "Завдання", "Термін", "Стан"]
  reportSql _ =
    "SELECT a.id, s.full_name, tp.title, a.title, DATE_FORMAT(a.deadline, '%d.%m.%Y'), a.status \
    \FROM assignments a \
    \JOIN topics tp ON tp.id = a.topic_id \
    \JOIN students s ON s.id = tp.student_id \
    \WHERE a.deadline < CURDATE() AND a.status NOT IN ('Здано','Зараховано') \
    \ORDER BY a.deadline"
  rowAction _ (i : _) = Just ("Редагувати", "/t/assignments/" <> valueText i <> "/edit")
  rowAction _ _       = Nothing

instance Report OpenQuestions where
  reportSlug _        = "open-questions"
  reportTitle _       = "Питання без відповіді"
  reportDescription _ = "Питання студентів, на які викладачі ще не відповіли."
  reportHeaders _     = ["id", "Студент", "Викладач", "Поставлено", "Питання"]
  reportSql _ =
    "SELECT q.id, s.full_name, t.full_name, DATE_FORMAT(q.asked_at, '%d.%m.%Y %H:%i'), q.question_text, q.teacher_id \
    \FROM questions q \
    \JOIN students s ON s.id = q.student_id \
    \JOIN teachers t ON t.id = q.teacher_id \
    \LEFT JOIN answers a ON a.question_id = q.id \
    \WHERE a.id IS NULL \
    \ORDER BY q.asked_at"
  rowAction _ (q : _ : _ : _ : _ : t : _) =
    Just ("Відповісти", "/t/answers/new?question_id=" <> valueText q <> "&teacher_id=" <> valueText t)
  rowAction _ _ = Nothing

instance Report UpcomingMeetings where
  reportSlug _        = "upcoming"
  reportTitle _       = "Найближчі зустрічі"
  reportDescription _ = "Графік консультацій, перевірок і захистів починаючи з сьогодні."
  reportHeaders _     = ["Дата", "Час", "Вид", "Тема", "Студент", "Викладач", "Де"]
  reportSql _ =
    "SELECT DATE_FORMAT(sc.meeting_date, '%d.%m.%Y'), \
    \  CONCAT(TIME_FORMAT(sc.start_time, '%H:%i'), '–', TIME_FORMAT(sc.end_time, '%H:%i')), \
    \  sc.kind, tp.title, s.full_name, t.full_name, COALESCE(sc.room, '') \
    \FROM schedule sc \
    \JOIN topics tp ON tp.id = sc.topic_id \
    \JOIN students s ON s.id = tp.student_id \
    \JOIN teachers t ON t.id = tp.teacher_id \
    \WHERE sc.meeting_date >= CURDATE() \
    \ORDER BY sc.meeting_date, sc.start_time"

instance Report TeacherLoad where
  reportSlug _        = "teacher-load"
  reportTitle _       = "Навантаження викладачів"
  reportDescription _ = "Скільки тем, студентів, запланованих зустрічей і питань припадає на кожного викладача."
  reportHeaders _     = ["Викладач", "Посада", "Тем", "Студентів", "Зустрічей", "Питань", "Відповідей"]
  reportSql _ =
    "SELECT t.full_name, t.position, \
    \  (SELECT COUNT(*) FROM topics tp WHERE tp.teacher_id = t.id), \
    \  (SELECT COUNT(DISTINCT tp.student_id) FROM topics tp WHERE tp.teacher_id = t.id), \
    \  (SELECT COUNT(*) FROM schedule sc JOIN topics tp ON tp.id = sc.topic_id WHERE tp.teacher_id = t.id), \
    \  (SELECT COUNT(*) FROM questions q WHERE q.teacher_id = t.id), \
    \  (SELECT COUNT(*) FROM answers a WHERE a.teacher_id = t.id) \
    \FROM teachers t ORDER BY t.full_name"

allReports :: [SomeReport]
allReports =
  [ SomeReport StudentProgress
  , SomeReport OverdueAssignments
  , SomeReport OpenQuestions
  , SomeReport UpcomingMeetings
  , SomeReport TeacherLoad
  ]

findReport :: Text -> Maybe SomeReport
findReport s = find (\(SomeReport r) -> reportSlug r == s) allReports
