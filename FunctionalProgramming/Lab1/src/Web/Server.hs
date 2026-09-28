{-# LANGUAGE RankNTypes          #-}
{-# LANGUAGE OverloadedStrings   #-}
{-# LANGUAGE ScopedTypeVariables #-}
-- | Маршрути веб-сервера (Scotty).
module Web.Server (runServer) where

import           Control.Exception      (SomeException, fromException, try)
import           Control.Monad          (forM)
import           Control.Monad.IO.Class (liftIO)
import           Data.Either            (lefts, rights)
import qualified Data.Map.Strict        as M
import           Data.Proxy             (Proxy (..))
import           Data.Text              (Text)
import qualified Data.Text              as T
import           Data.Text.Encoding     (decodeUtf8With)
import           Data.Text.Encoding.Error (lenientDecode)
import qualified Data.Text.Lazy         as TL
import           Data.Time              (defaultTimeLocale, formatTime, getZonedTime, zonedTimeToLocalTime)
import           Database.MySQL.Base    (ConnectInfo, ERR (..), ERRException (..), MySQLConn)
import           Lucid                  (Html, renderText)
import           Network.HTTP.Types     (status404, status500)
import           Web.Scotty

import           Db
import           Model.Entities
import           Model.Entity
import           Model.Field
import           Model.Report
import           Web.View

runServer :: Int -> ConnectInfo -> IO ()
runServer port ci = scotty port $ do
  get "/" $ do
    counts <- db ci $ \c -> forM allEntities $ \e -> (,) e <$> countRows c (entityTable e)
    page (dashboardPage counts)

  get "/t/:table" $ withTable $ \p -> do
    mq <- qParam "q"
    mf <- qParam "msg"
    tv <- db ci $ \c -> tableView c p mq
    page (listPage tv mq mf)

  get "/t/:table/new" $ withTable $ \p -> do
    qs  <- strictParams <$> queryParams
    now <- liftIO getZonedTime
    let stamp    = T.pack (formatTime defaultTimeLocale "%Y-%m-%dT%H:%M" (zonedTimeToLocalTime now))
        defaults = M.fromList [ (fieldName f, stamp) | f <- fields p, fieldType f == FDateTime ]
    showForm p Nothing (M.union (M.fromList qs) defaults) []

  post "/t/:table/new" $ withTable $ \p -> do
    raw <- M.fromList . strictParams <$> formParams
    case buildRecord p 0 raw of
      Left errs -> showForm p Nothing raw errs
      Right x -> do
        r <- liftIO (try (withConn ci (\c -> insertRow c x)))
        case r of
          Left e  -> showForm p Nothing raw [dbErrorText e]
          Right _ -> redirect (TL.fromStrict ("/t/" <> tableName p <> "?msg=created"))

  get "/t/:table/:id/edit" $ withTable $ \p -> do
    i  <- captureParam "id"
    mx <- db ci $ \c -> fetchOne c p i
    case mx of
      Nothing -> notFoundPage
      Just x  -> showForm p (Just i) (M.fromList (zip (map fieldName (fields p)) (map inputValue (toRow x)))) []

  post "/t/:table/:id/edit" $ withTable $ \p -> do
    i   <- captureParam "id"
    raw <- M.fromList . strictParams <$> formParams
    case buildRecord p i raw of
      Left errs -> showForm p (Just i) raw errs
      Right x -> do
        r <- liftIO (try (withConn ci (\c -> updateRow c x)))
        case r of
          Left e   -> showForm p (Just i) raw [dbErrorText e]
          Right () -> redirect (TL.fromStrict ("/t/" <> tableName p <> "?msg=saved"))

  post "/t/:table/:id/delete" $ withTable $ \p -> do
    i <- captureParam "id"
    db ci $ \c -> deleteRow c (tableName p) i
    redirect (TL.fromStrict ("/t/" <> tableName p <> "?msg=deleted"))

  get "/search" $ do
    q <- maybe "" T.strip <$> qParam "q"
    if T.null q
      then redirect "/"
      else do
        tvs <- db ci $ \c -> forM allEntities $ \(SomeEntity p) -> tableView c p (Just q)
        page (searchPage q tvs)

  get "/reports" $ page reportsPage

  get "/reports/:slug" $ do
    s <- captureParam "slug"
    case findReport s of
      Nothing -> notFoundPage
      Just (SomeReport r) -> do
        rows <- db ci $ \c -> runReport c r
        page (reportPage r rows)

  notFound notFoundPage
  where
    -- | Знайти сутність за назвою таблиці з URL і передати її обробнику.
    withTable :: (forall a. Entity a => Proxy a -> ActionM ()) -> ActionM ()
    withTable k = do
      t <- captureParam "table"
      maybe notFoundPage (\(SomeEntity p) -> k p) (findEntity t)

    showForm :: forall a. Entity a => Proxy a -> Maybe Int -> M.Map Text Text -> [Text] -> ActionM ()
    showForm p mid vals errs = do
      refs <- db ci $ \c -> refMaps c (fields p)
      let (heading, url) = case mid of
            Nothing -> ("Додати " <> singularTitle p, "/t/" <> tableName p <> "/new")
            Just i  -> ( "Редагувати " <> singularTitle p <> " №" <> T.pack (show i)
                       , "/t/" <> tableName p <> "/" <> T.pack (show i) <> "/edit" )
      page (formPage (tableName p) heading (fields p) refs vals errs url)

-- | Необов'язковий параметр рядка запиту.
qParam :: Text -> ActionM (Maybe Text)
qParam k = fmap TL.toStrict . lookup (TL.fromStrict k) <$> queryParams

strictParams :: [(TL.Text, TL.Text)] -> [(Text, Text)]
strictParams = map (\(k, v) -> (TL.toStrict k, TL.toStrict v))

page :: Html () -> ActionM ()
page = html . renderText

notFoundPage :: ActionM ()
notFoundPage = status status404 >> page (messagePage "Не знайдено" "Сторінку або запис не знайдено.")

-- | Виконати дію з БД; у разі помилки показати сторінку з повідомленням.
db :: ConnectInfo -> (MySQLConn -> IO a) -> ActionM a
db ci act = do
  r <- liftIO (try (withConn ci act))
  case r of
    Right x -> pure x
    Left e  -> do
      status status500
      page (messagePage "Помилка бази даних" (dbErrorText e))
      finish

tableView :: forall a. Entity a => MySQLConn -> Proxy a -> Maybe Text -> IO TableView
tableView c p mq = do
  xs   <- fetchList c p mq
  refs <- refMaps c (fields p)
  pure TableView
    { tvTable  = tableName p
    , tvTitle  = pluralTitle p
    , tvFields = fields p
    , tvRefs   = refs
    , tvRows   = [ (entityKey x, toRow x) | x <- xs ]
    }

-- | Текст форми -> типізований запис (розбір полів, fromRow, validate).
buildRecord :: forall a. Entity a => Proxy a -> Int -> M.Map Text Text -> Either [Text] a
buildRecord p i raw
  | not (null errs) = Left errs
  | otherwise = case fromRow i (rights parsed) of
      Left e  -> Left [e]
      Right x -> case validate x of
        [] -> Right x
        es -> Left es
  where
    parsed = [ parseInput f (M.findWithDefault "" (fieldName f) raw) | f <- fields p ]
    errs   = lefts parsed

dbErrorText :: SomeException -> Text
dbErrorText e = case fromException e of
  Just (ERRException er) -> case errCode er of
    1451 -> "Запис неможливо видалити/змінити: на нього посилаються інші записи (спершу видаліть або змініть їх)."
    1452 -> "Вказано посилання на запис, якого не існує."
    1062 -> "Такий запис уже існує."
    _    -> "MySQL: " <> decodeUtf8With lenientDecode (errMsg er)
  Nothing -> "Не вдалося виконати операцію з базою даних: " <> T.pack (show e)
