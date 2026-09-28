{-# LANGUAGE OverloadedStrings #-}
-- | Опис полів таблиць та перетворення значень між Haskell, MySQL та HTML-формами.
module Model.Field
  ( FieldType (..)
  , Field (..)
  , req
  , opt
  , detail
  , DbValue (..)
  , parseInput
  , displayValue
  , inputValue
  , valueText
  ) where

import           Data.Int            (Int16, Int32, Int64, Int8)
import           Data.Text           (Text)
import qualified Data.Text           as T
import           Data.Text.Encoding  (decodeUtf8With)
import           Data.Text.Encoding.Error (lenientDecode)
import           Data.Time
import           Data.Word           (Word16, Word32, Word64, Word8)
import           Database.MySQL.Base (MySQLValue (..))
import           Text.Read           (readMaybe)

-- | Тип поля визначає, як воно зберігається, відображається та вводиться.
data FieldType
  = FText          -- ^ короткий рядок
  | FLongText      -- ^ багаторядковий текст
  | FInt           -- ^ ціле число
  | FDate          -- ^ дата
  | FTime          -- ^ час
  | FDateTime      -- ^ дата і час
  | FEnum [Text]   -- ^ одне значення з переліку
  | FRef Text      -- ^ зовнішній ключ (ім'я таблиці, на яку посилається)
  deriving (Show, Eq)

data Field = Field
  { fieldName     :: Text      -- ^ назва стовпця в БД
  , fieldLabel    :: Text      -- ^ підпис в інтерфейсі
  , fieldType     :: FieldType
  , fieldRequired :: Bool
  , fieldInList   :: Bool      -- ^ чи показувати стовпець у таблиці-списку
  }

-- | Обов'язкове поле.
req :: Text -> Text -> FieldType -> Field
req n l t = Field n l t True True

-- | Необов'язкове поле.
opt :: Text -> Text -> FieldType -> Field
opt n l t = Field n l t False True

-- | Поле, що показується лише у формі редагування (довгі тексти тощо).
detail :: Field -> Field
detail f = f { fieldInList = False }

------------------------------------------------------------------------------
-- Клас типів, значення яких можна зберігати в MySQL

class DbValue a where
  toDb   :: a -> MySQLValue
  fromDb :: MySQLValue -> Either Text a

instance DbValue Text where
  toDb = MySQLText
  fromDb (MySQLText t)  = Right t
  fromDb (MySQLBytes b) = Right (decodeUtf8With lenientDecode b)
  fromDb v              = Left ("очікувався текст, отримано " <> T.pack (show v))

instance DbValue Int where
  toDb = MySQLInt64 . fromIntegral
  fromDb v = case v of
    MySQLInt8 n   -> Right (fromIntegral (n :: Int8))
    MySQLInt8U n  -> Right (fromIntegral (n :: Word8))
    MySQLInt16 n  -> Right (fromIntegral (n :: Int16))
    MySQLInt16U n -> Right (fromIntegral (n :: Word16))
    MySQLInt32 n  -> Right (fromIntegral (n :: Int32))
    MySQLInt32U n -> Right (fromIntegral (n :: Word32))
    MySQLInt64 n  -> Right (fromIntegral (n :: Int64))
    MySQLInt64U n -> Right (fromIntegral (n :: Word64))
    _             -> Left ("очікувалось ціле число, отримано " <> T.pack (show v))

instance DbValue Day where
  toDb = MySQLDate
  fromDb (MySQLDate d) = Right d
  fromDb v             = Left ("очікувалась дата, отримано " <> T.pack (show v))

instance DbValue TimeOfDay where
  toDb = MySQLTime 0
  fromDb (MySQLTime _ t) = Right t
  fromDb v               = Left ("очікувався час, отримано " <> T.pack (show v))

instance DbValue LocalTime where
  toDb = MySQLDateTime
  fromDb (MySQLDateTime t)  = Right t
  fromDb (MySQLTimeStamp t) = Right t
  fromDb v                  = Left ("очікувались дата й час, отримано " <> T.pack (show v))

-- | NULL у базі відповідає Nothing.
instance DbValue a => DbValue (Maybe a) where
  toDb = maybe MySQLNull toDb
  fromDb MySQLNull = Right Nothing
  fromDb v         = Just <$> fromDb v

------------------------------------------------------------------------------
-- Розбір введених у форму значень

-- | Перетворює текст із HTML-форми у значення MySQL відповідно до типу поля.
parseInput :: Field -> Text -> Either Text MySQLValue
parseInput f raw
  | T.null s  = if fieldRequired f
                  then Left ("Поле «" <> fieldLabel f <> "» є обов'язковим")
                  else Right MySQLNull
  | otherwise = case fieldType f of
      FText     -> Right (MySQLText s)
      FLongText -> Right (MySQLText s)
      FInt      -> num
      FRef _    -> num
      FDate     -> maybe (bad "дата") (Right . MySQLDate)    (parseAny ["%Y-%m-%d", "%d.%m.%Y"])
      FTime     -> maybe (bad "час")  (Right . MySQLTime 0) (parseAny ["%H:%M:%S", "%H:%M"])
      FDateTime -> maybe (bad "дата й час") (Right . MySQLDateTime)
                     (parseAny ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"])
      FEnum vs
        | s `elem` vs -> Right (MySQLText s)
        | otherwise   -> Left ("Недопустиме значення поля «" <> fieldLabel f <> "»")
  where
    s = T.strip raw
    bad what = Left ("Поле «" <> fieldLabel f <> "»: некоректна " <> what <> " (" <> s <> ")")
    num = maybe (bad "кількість") (Right . MySQLInt64) (readMaybe (T.unpack s))
    parseAny :: ParseTime t => [String] -> Maybe t
    parseAny fmts = case [x | fmt <- fmts, Just x <- [parseTimeM True defaultTimeLocale fmt (T.unpack s)]] of
      (x : _) -> Just x
      []      -> Nothing

------------------------------------------------------------------------------
-- Відображення значень

fmt :: FormatTime t => String -> t -> Text
fmt f = T.pack . formatTime defaultTimeLocale f

-- | Значення для показу користувачу.
displayValue :: MySQLValue -> Text
displayValue v = case v of
  MySQLNull         -> "—"
  MySQLDate d       -> fmt "%d.%m.%Y" d
  MySQLTime _ t     -> fmt "%H:%M" t
  MySQLDateTime t   -> fmt "%d.%m.%Y %H:%M" t
  MySQLTimeStamp t  -> fmt "%d.%m.%Y %H:%M" t
  _                 -> valueText v

-- | Значення у форматі, який приймає відповідний елемент HTML-форми.
inputValue :: MySQLValue -> Text
inputValue v = case v of
  MySQLNull        -> ""
  MySQLDate d      -> fmt "%Y-%m-%d" d
  MySQLTime _ t    -> fmt "%H:%M" t
  MySQLDateTime t  -> fmt "%Y-%m-%dT%H:%M" t
  MySQLTimeStamp t -> fmt "%Y-%m-%dT%H:%M" t
  _                -> valueText v

-- | Універсальне текстове подання значення.
valueText :: MySQLValue -> Text
valueText v = case v of
  MySQLNull    -> ""
  MySQLText t  -> t
  MySQLBytes b -> decodeUtf8With lenientDecode b
  _ -> case (fromDb v :: Either Text Int) of
         Right n -> T.pack (show n)
         Left _  -> T.pack (show v)
