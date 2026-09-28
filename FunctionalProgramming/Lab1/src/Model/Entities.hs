{-# LANGUAGE OverloadedStrings #-}
-- | Типи даних предметної області «Індивідуальна робота кафедри зі студентами»
-- та їх екземпляри класу 'Entity'.
module Model.Entities
  ( Teacher (..)
  , Student (..)
  , Topic (..)
  , Schedule (..)
  , Assignment (..)
  , Material (..)
  , Question (..)
  , Answer (..)
  , allEntities
  , findEntity
  , topicStatuses
  , meetingKinds
  , assignmentStatuses
  , materialTypes
  ) where

import           Data.List           (find)
import           Data.Proxy          (Proxy (..))
import           Data.Text           (Text)
import           Data.Time           (Day, LocalTime, TimeOfDay)

import           Model.Entity
import           Model.Field

badRow :: Text -> Either Text a
badRow t = Left ("Некоректний рядок таблиці " <> t)

------------------------------------------------------------------------------
-- 1. Викладачі

data Teacher = Teacher
  { teacherId       :: Int
  , teacherName     :: Text
  , teacherPosition :: Text
  , teacherDegree   :: Maybe Text
  , teacherEmail    :: Maybe Text
  , teacherPhone    :: Maybe Text
  } deriving (Show)

instance Entity Teacher where
  tableName _     = "teachers"
  pluralTitle _   = "Викладачі"
  singularTitle _ = "викладача"
  labelColumns _  = ["full_name"]
  fields _ =
    [ req "full_name" "ПІБ"              FText
    , req "position"  "Посада"           (FEnum ["Асистент", "Старший викладач", "Доцент", "Професор", "Завідувач кафедри"])
    , opt "degree"    "Науковий ступінь" FText
    , opt "email"     "E-mail"           FText
    , opt "phone"     "Телефон"          FText
    ]
  entityKey = teacherId
  toRow t = [toDb (teacherName t), toDb (teacherPosition t), toDb (teacherDegree t), toDb (teacherEmail t), toDb (teacherPhone t)]
  fromRow i [a, b, c, d, e] = Teacher i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e
  fromRow _ _ = badRow "teachers"

------------------------------------------------------------------------------
-- 2. Студенти

data Student = Student
  { studentId     :: Int
  , studentName   :: Text
  , studentGroup  :: Text
  , studentCourse :: Int
  , studentEmail  :: Maybe Text
  , studentPhone  :: Maybe Text
  } deriving (Show)

instance Entity Student where
  tableName _     = "students"
  pluralTitle _   = "Студенти"
  singularTitle _ = "студента"
  labelColumns _  = ["full_name", "group_name"]
  fields _ =
    [ req "full_name"  "ПІБ"     FText
    , req "group_name" "Група"   FText
    , req "course"     "Курс"    FInt
    , opt "email"      "E-mail"  FText
    , opt "phone"      "Телефон" FText
    ]
  entityKey = studentId
  toRow s = [toDb (studentName s), toDb (studentGroup s), toDb (studentCourse s), toDb (studentEmail s), toDb (studentPhone s)]
  fromRow i [a, b, c, d, e] = Student i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e
  fromRow _ _ = badRow "students"
  validate s = [ "Курс має бути від 1 до 6" | studentCourse s < 1 || studentCourse s > 6 ]

------------------------------------------------------------------------------
-- 3. Теми індивідуальної роботи

topicStatuses :: [Text]
topicStatuses = ["Заплановано", "В роботі", "Завершено", "Скасовано"]

data Topic = Topic
  { topicId          :: Int
  , topicTitle       :: Text
  , topicDescription :: Maybe Text
  , topicTeacher     :: Int
  , topicStudent     :: Int
  , topicStart       :: Day
  , topicEnd         :: Day
  , topicStatus      :: Text
  } deriving (Show)

instance Entity Topic where
  tableName _     = "topics"
  pluralTitle _   = "Теми"
  singularTitle _ = "тему"
  labelColumns _  = ["title"]
  fields _ =
    [ req "title"       "Тема"        FText
    , detail (opt "description" "Опис" FLongText)
    , req "teacher_id"  "Керівник"    (FRef "teachers")
    , req "student_id"  "Студент"     (FRef "students")
    , req "start_date"  "Початок"     FDate
    , req "end_date"    "Завершення"  FDate
    , req "status"      "Статус"      (FEnum topicStatuses)
    ]
  entityKey = topicId
  toRow t = [ toDb (topicTitle t), toDb (topicDescription t), toDb (topicTeacher t), toDb (topicStudent t)
            , toDb (topicStart t), toDb (topicEnd t), toDb (topicStatus t) ]
  fromRow i [a, b, c, d, e, f, g] =
    Topic i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e <*> fromDb f <*> fromDb g
  fromRow _ _ = badRow "topics"
  validate t = [ "Дата завершення не може бути раніше дати початку" | topicEnd t < topicStart t ]

------------------------------------------------------------------------------
-- 4. Графік роботи (консультації, перевірки, захисти)

meetingKinds :: [Text]
meetingKinds = ["Консультація", "Перевірка завдання", "Захист", "Онлайн-зустріч"]

data Schedule = Schedule
  { scheduleId    :: Int
  , scheduleTopic :: Int
  , scheduleDate  :: Day
  , scheduleStart :: TimeOfDay
  , scheduleEnd   :: TimeOfDay
  , scheduleRoom  :: Maybe Text
  , scheduleKind  :: Text
  , scheduleNote  :: Maybe Text
  } deriving (Show)

instance Entity Schedule where
  tableName _     = "schedule"
  pluralTitle _   = "Графік роботи"
  singularTitle _ = "зустріч"
  labelColumns _  = ["meeting_date", "start_time"]
  fields _ =
    [ req "topic_id"     "Тема"            (FRef "topics")
    , req "meeting_date" "Дата"            FDate
    , req "start_time"   "Початок"         FTime
    , req "end_time"     "Кінець"          FTime
    , opt "room"         "Аудиторія / посилання" FText
    , req "kind"         "Вид"             (FEnum meetingKinds)
    , detail (opt "note" "Примітка" FLongText)
    ]
  entityKey = scheduleId
  toRow s = [ toDb (scheduleTopic s), toDb (scheduleDate s), toDb (scheduleStart s), toDb (scheduleEnd s)
            , toDb (scheduleRoom s), toDb (scheduleKind s), toDb (scheduleNote s) ]
  fromRow i [a, b, c, d, e, f, g] =
    Schedule i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e <*> fromDb f <*> fromDb g
  fromRow _ _ = badRow "schedule"
  validate s = [ "Час завершення має бути пізніше часу початку" | scheduleEnd s <= scheduleStart s ]

------------------------------------------------------------------------------
-- 5. Завдання та їх виконання

assignmentStatuses :: [Text]
assignmentStatuses = ["Видано", "В процесі", "Здано", "На доопрацюванні", "Зараховано"]

data Assignment = Assignment
  { assignmentId       :: Int
  , assignmentTopic    :: Int
  , assignmentTitle    :: Text
  , assignmentText     :: Maybe Text
  , assignmentDeadline :: Day
  , assignmentStatus   :: Text
  , assignmentSubmitted :: Maybe Day
  , assignmentGrade    :: Maybe Int
  , assignmentComment  :: Maybe Text
  } deriving (Show)

instance Entity Assignment where
  tableName _     = "assignments"
  pluralTitle _   = "Виконання завдань"
  singularTitle _ = "завдання"
  labelColumns _  = ["title"]
  fields _ =
    [ req "topic_id"        "Тема"            (FRef "topics")
    , req "title"           "Завдання"        FText
    , detail (opt "description" "Опис завдання" FLongText)
    , req "deadline"        "Термін"          FDate
    , req "status"          "Стан"            (FEnum assignmentStatuses)
    , opt "submitted_on"    "Дата здачі"      FDate
    , opt "grade"           "Оцінка (0–100)"  FInt
    , detail (opt "teacher_comment" "Коментар викладача" FLongText)
    ]
  entityKey = assignmentId
  toRow a = [ toDb (assignmentTopic a), toDb (assignmentTitle a), toDb (assignmentText a), toDb (assignmentDeadline a)
            , toDb (assignmentStatus a), toDb (assignmentSubmitted a), toDb (assignmentGrade a), toDb (assignmentComment a) ]
  fromRow i [a, b, c, d, e, f, g, h] =
    Assignment i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e <*> fromDb f <*> fromDb g <*> fromDb h
  fromRow _ _ = badRow "assignments"
  validate a =
    [ "Оцінка має бути в межах 0–100" | Just g <- [assignmentGrade a], g < 0 || g > 100 ] ++
    [ "Для статусу «Зараховано» потрібно вказати оцінку"
    | assignmentStatus a == "Зараховано", assignmentGrade a == Nothing ] ++
    [ "Для зданого завдання вкажіть дату здачі"
    | assignmentStatus a `elem` ["Здано", "Зараховано"], assignmentSubmitted a == Nothing ]

------------------------------------------------------------------------------
-- 6. Допоміжні інформаційні матеріали до тем

materialTypes :: [Text]
materialTypes = ["Література", "Стаття", "Методичка", "Відео", "Презентація", "Приклад коду", "Інше"]

data Material = Material
  { materialId    :: Int
  , materialTopic :: Int
  , materialTitle :: Text
  , materialType  :: Text
  , materialUrl   :: Maybe Text
  , materialDescr :: Maybe Text
  } deriving (Show)

instance Entity Material where
  tableName _     = "materials"
  pluralTitle _   = "Матеріали"
  singularTitle _ = "матеріал"
  labelColumns _  = ["title"]
  fields _ =
    [ req "topic_id"      "Тема"             (FRef "topics")
    , req "title"         "Назва"            FText
    , req "material_type" "Вид"              (FEnum materialTypes)
    , opt "url"           "Посилання / файл" FText
    , detail (opt "description" "Опис" FLongText)
    ]
  entityKey = materialId
  toRow m = [toDb (materialTopic m), toDb (materialTitle m), toDb (materialType m), toDb (materialUrl m), toDb (materialDescr m)]
  fromRow i [a, b, c, d, e] = Material i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e
  fromRow _ _ = badRow "materials"

------------------------------------------------------------------------------
-- 7. Питання студентів

data Question = Question
  { questionId      :: Int
  , questionStudent :: Int
  , questionTeacher :: Int
  , questionTopic   :: Maybe Int
  , questionText    :: Text
  , questionAsked   :: LocalTime
  } deriving (Show)

instance Entity Question where
  tableName _     = "questions"
  pluralTitle _   = "Питання студентів"
  singularTitle _ = "питання"
  labelColumns _  = ["question_text"]
  fields _ =
    [ req "student_id"    "Студент"         (FRef "students")
    , req "teacher_id"    "Кому (викладач)" (FRef "teachers")
    , opt "topic_id"      "Тема"            (FRef "topics")
    , req "question_text" "Питання"         FLongText
    , req "asked_at"      "Поставлено"      FDateTime
    ]
  entityKey = questionId
  toRow q = [toDb (questionStudent q), toDb (questionTeacher q), toDb (questionTopic q), toDb (questionText q), toDb (questionAsked q)]
  fromRow i [a, b, c, d, e] = Question i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d <*> fromDb e
  fromRow _ _ = badRow "questions"

------------------------------------------------------------------------------
-- 8. Відповіді викладачів

data Answer = Answer
  { answerId       :: Int
  , answerQuestion :: Int
  , answerTeacher  :: Int
  , answerText     :: Text
  , answerAt       :: LocalTime
  } deriving (Show)

instance Entity Answer where
  tableName _     = "answers"
  pluralTitle _   = "Відповіді викладачів"
  singularTitle _ = "відповідь"
  labelColumns _  = ["answer_text"]
  fields _ =
    [ req "question_id" "Питання"   (FRef "questions")
    , req "teacher_id"  "Викладач"  (FRef "teachers")
    , req "answer_text" "Відповідь" FLongText
    , req "answered_at" "Дата"      FDateTime
    ]
  entityKey = answerId
  toRow a = [toDb (answerQuestion a), toDb (answerTeacher a), toDb (answerText a), toDb (answerAt a)]
  fromRow i [a, b, c, d] = Answer i <$> fromDb a <*> fromDb b <*> fromDb c <*> fromDb d
  fromRow _ _ = badRow "answers"

------------------------------------------------------------------------------

-- | Усі таблиці системи (порядок = порядок у меню).
allEntities :: [SomeEntity]
allEntities =
  [ SomeEntity (Proxy :: Proxy Student)
  , SomeEntity (Proxy :: Proxy Teacher)
  , SomeEntity (Proxy :: Proxy Topic)
  , SomeEntity (Proxy :: Proxy Schedule)
  , SomeEntity (Proxy :: Proxy Assignment)
  , SomeEntity (Proxy :: Proxy Material)
  , SomeEntity (Proxy :: Proxy Question)
  , SomeEntity (Proxy :: Proxy Answer)
  ]

findEntity :: Text -> Maybe SomeEntity
findEntity t = find ((== t) . entityTable) allEntities

