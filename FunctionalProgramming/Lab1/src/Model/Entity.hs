{-# LANGUAGE ExistentialQuantification #-}
{-# LANGUAGE OverloadedStrings         #-}
-- | Клас сутностей інформаційної системи. Кожна таблиця БД описується
-- окремим типом-записом та його екземпляром (instance) класу 'Entity'.
module Model.Entity
  ( Entity (..)
  , SomeEntity (..)
  , entityTable
  , entityPlural
  , entityFields
  ) where

import           Data.Proxy          (Proxy (..))
import           Data.Text           (Text)
import           Database.MySQL.Base (MySQLValue)

import           Model.Field

class Entity a where
  -- | Назва таблиці в MySQL.
  tableName     :: Proxy a -> Text
  -- | Назви для інтерфейсу.
  pluralTitle   :: Proxy a -> Text
  singularTitle :: Proxy a -> Text
  -- | Поля таблиці (крім первинного ключа id) у порядку стовпців.
  fields        :: Proxy a -> [Field]
  -- | Стовпці, з яких складається підпис запису у випадаючих списках.
  labelColumns  :: Proxy a -> [Text]

  -- | Первинний ключ запису.
  entityKey     :: a -> Int
  -- | Запис -> значення стовпців (у порядку 'fields').
  toRow         :: a -> [MySQLValue]
  -- | id та значення стовпців -> запис (з перевіркою типів).
  fromRow       :: Int -> [MySQLValue] -> Either Text a

  -- | Перевірка бізнес-правил; повертає список помилок.
  validate      :: a -> [Text]
  validate _ = []

-- | Сутність довільного типу — щоб тримати всі таблиці в одному списку.
data SomeEntity = forall a. Entity a => SomeEntity (Proxy a)

entityTable :: SomeEntity -> Text
entityTable (SomeEntity p) = tableName p

entityPlural :: SomeEntity -> Text
entityPlural (SomeEntity p) = pluralTitle p

entityFields :: SomeEntity -> [Field]
entityFields (SomeEntity p) = fields p
