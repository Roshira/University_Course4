{-# LANGUAGE OverloadedStrings   #-}
{-# LANGUAGE ScopedTypeVariables #-}
-- | Робота з MySQL: підключення та універсальні CRUD-операції для будь-якої 'Entity'.
module Db
  ( loadConnectInfo
  , withConn
  , fetchList
  , fetchOne
  , insertRow
  , updateRow
  , deleteRow
  , refOptions
  , refMaps
  , countRows
  , runReport
  ) where

import           Control.Exception    (bracket)
import           Control.Monad        (forM, void)
import qualified Data.ByteString.Char8 as BC
import qualified Data.ByteString.Lazy as LBS
import           Data.Map.Strict      (Map)
import qualified Data.Map.Strict      as M
import           Data.Maybe           (fromMaybe)
import           Data.Proxy           (Proxy (..))
import           Data.Text            (Text)
import qualified Data.Text            as T
import           Data.Text.Encoding   (encodeUtf8)
import           Database.MySQL.Base
import           System.Environment   (lookupEnv)
import qualified System.IO.Streams    as Streams
import           Text.Read            (readMaybe)

import           Model.Entities       (findEntity)
import           Model.Entity
import           Model.Field
import           Model.Report

-- | Параметри підключення беруться зі змінних середовища (із значеннями за замовчуванням).
loadConnectInfo :: IO ConnectInfo
loadConnectInfo = do
  host <- env "MYSQL_HOST"     "127.0.0.1"
  port <- env "MYSQL_PORT"     "3306"
  user <- env "MYSQL_USER"     "lab1"
  pass <- env "MYSQL_PASSWORD" "lab1pass"
  db   <- env "MYSQL_DATABASE" "individual_work"
  pure defaultConnectInfoMB4
    { ciHost     = host
    , ciPort     = maybe 3306 fromInteger (readMaybe port)
    , ciUser     = BC.pack user
    , ciPassword = BC.pack pass
    , ciDatabase = BC.pack db
    }
  where env k d = fromMaybe d <$> lookupEnv k

-- | Окреме підключення на кожен запит — MySQLConn не є потокобезпечним.
withConn :: ConnectInfo -> (MySQLConn -> IO a) -> IO a
withConn ci act = bracket (connect ci) close $ \c -> do
  void (execute_ c "SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
  act c

sql :: Text -> Query
sql = Query . LBS.fromStrict . encodeUtf8

selectRows :: MySQLConn -> Text -> [MySQLValue] -> IO [[MySQLValue]]
selectRows c q [] = query_ c (sql q) >>= Streams.toList . snd
selectRows c q ps = query c (sql q) ps >>= Streams.toList . snd

------------------------------------------------------------------------------
-- Генерація SQL за описом полів

-- | SELECT усіх полів із LEFT JOIN на таблиці-довідники (щоб шукати за їх назвами).
selectSql :: forall a. Entity a => Proxy a -> [Text] -> Text
selectSql p conds =
  "SELECT " <> T.intercalate ", " (map ("t." <>) ("id" : map fieldName fs))
    <> " FROM " <> tableName p <> " t"
    <> T.concat joins
    <> (if null conds then "" else " WHERE " <> T.intercalate " AND " conds)
    <> " ORDER BY t.id DESC"
  where
    fs = fields p
    refs = [ (alias, rt, fieldName f) | (n, f) <- zip [1 :: Int ..] fs, FRef rt <- [fieldType f]
                                      , let alias = "r" <> T.pack (show n) ]
    joins = [ " LEFT JOIN " <> rt <> " " <> al <> " ON " <> al <> ".id = t." <> col | (al, rt, col) <- refs ]

-- | Вираз, що склеює всі текстові подання рядка (для пошуку LIKE).
searchExpr :: forall a. Entity a => Proxy a -> Text
searchExpr p = "CONCAT_WS(' ', " <> T.intercalate ", " (map cast (own ++ refCols)) <> ")"
  where
    fs = fields p
    own = map (("t." <>) . fieldName) fs
    refCols = [ "r" <> T.pack (show n) <> "." <> lc
              | (n, f) <- zip [1 :: Int ..] fs, FRef rt <- [fieldType f], lc <- labelsOf rt ]
    cast e = "CAST(" <> e <> " AS CHAR)"

labelsOf :: Text -> [Text]
labelsOf rt = maybe ["id"] (\(SomeEntity q) -> labelColumns q) (findEntity rt)

decodeRow :: forall a. Entity a => Proxy a -> [MySQLValue] -> IO a
decodeRow p (iv : vs) =
  case fromDb iv >>= \i -> fromRow i vs of
    Right x  -> pure x
    Left err -> ioError (userError (T.unpack (tableName p <> ": " <> err)))
decodeRow p [] = ioError (userError (T.unpack (tableName p <> ": порожній рядок")))

------------------------------------------------------------------------------
-- CRUD

-- | Список записів; якщо задано рядок пошуку — лише ті, що його містять.
fetchList :: forall a. Entity a => MySQLConn -> Proxy a -> Maybe Text -> IO [a]
fetchList c p mq = do
  rows <- case T.strip <$> mq of
    Just q | not (T.null q) ->
      selectRows c (selectSql p [searchExpr p <> " LIKE ?"]) [MySQLText ("%" <> q <> "%")]
    _ -> selectRows c (selectSql p []) []
  mapM (decodeRow p) rows

fetchOne :: forall a. Entity a => MySQLConn -> Proxy a -> Int -> IO (Maybe a)
fetchOne c p i = do
  rows <- selectRows c (selectSql p ["t.id = ?"]) [MySQLInt64 (fromIntegral i)]
  case rows of
    (r : _) -> Just <$> decodeRow p r
    []      -> pure Nothing

insertRow :: forall a. Entity a => MySQLConn -> a -> IO Int
insertRow c x = do
  let p = Proxy :: Proxy a
      cols = map fieldName (fields p)
      q = "INSERT INTO " <> tableName p <> " (" <> T.intercalate ", " cols <> ") VALUES ("
            <> T.intercalate ", " (map (const "?") cols) <> ")"
  ok <- execute c (sql q) (toRow x)
  pure (okLastInsertID ok)

updateRow :: forall a. Entity a => MySQLConn -> a -> IO ()
updateRow c x = do
  let p = Proxy :: Proxy a
      sets = T.intercalate ", " [ fieldName f <> " = ?" | f <- fields p ]
      q = "UPDATE " <> tableName p <> " SET " <> sets <> " WHERE id = ?"
  void (execute c (sql q) (toRow x ++ [MySQLInt64 (fromIntegral (entityKey x))]))

deleteRow :: MySQLConn -> Text -> Int -> IO ()
deleteRow c table i =
  void (execute c (sql ("DELETE FROM " <> table <> " WHERE id = ?")) [MySQLInt64 (fromIntegral i)])

countRows :: MySQLConn -> Text -> IO Int
countRows c table = do
  rows <- selectRows c ("SELECT COUNT(*) FROM " <> table) []
  pure $ case rows of
    [[v]] -> either (const 0) id (fromDb v)
    _     -> 0

-- | Варіанти для випадаючого списку зовнішнього ключа: (id, підпис).
refOptions :: MySQLConn -> Text -> IO [(Int, Text)]
refOptions c rt = do
  let lbl = "CONCAT_WS(' · ', " <> T.intercalate ", " [ "CAST(" <> l <> " AS CHAR)" | l <- labelsOf rt ] <> ")"
  rows <- selectRows c ("SELECT id, " <> lbl <> " FROM " <> rt <> " ORDER BY 2") []
  pure [ (i, shorten (valueText l)) | [iv, l] <- rows, Right i <- [fromDb iv] ]
  where shorten t = if T.length t > 90 then T.take 87 t <> "…" else t

-- | Словники підписів для всіх зовнішніх ключів сутності (ключ — назва поля).
refMaps :: MySQLConn -> [Field] -> IO (Map Text [(Int, Text)])
refMaps c fs = M.fromList <$> forM [ (fieldName f, rt) | f <- fs, FRef rt <- [fieldType f] ]
  (\(n, rt) -> (,) n <$> refOptions c rt)

-- | Виконати звіт: повертає рядки значень.
runReport :: Report r => MySQLConn -> r -> IO [[MySQLValue]]
runReport c r = selectRows c (reportSql r) []
