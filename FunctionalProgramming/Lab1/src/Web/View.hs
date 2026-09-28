{-# LANGUAGE OverloadedStrings #-}
-- | HTML-сторінки веб-інтерфейсу (бібліотека lucid).
module Web.View
  ( TableView (..)
  , layout
  , dashboardPage
  , listPage
  , formPage
  , searchPage
  , reportsPage
  , reportPage
  , messagePage
  ) where

import           Control.Monad       (forM_, unless, when)
import           Data.Map.Strict     (Map)
import qualified Data.Map.Strict     as M
import           Data.Maybe          (fromMaybe)
import           Data.Text           (Text)
import qualified Data.Text           as T
import           Database.MySQL.Base (MySQLValue (..))
import           Lucid

import           Model.Entities      (allEntities)
import           Model.Entity
import           Model.Field
import           Model.Report

-- | Усе, що потрібно для показу таблиці однієї сутності.
data TableView = TableView
  { tvTable  :: Text
  , tvTitle  :: Text
  , tvFields :: [Field]
  , tvRefs   :: Map Text [(Int, Text)]
  , tvRows   :: [(Int, [MySQLValue])]
  }

------------------------------------------------------------------------------

layout :: Text -> Html () -> Html ()
layout title body = doctypehtml_ $ do
  head_ $ do
    meta_ [charset_ "utf-8"]
    meta_ [name_ "viewport", content_ "width=device-width, initial-scale=1"]
    title_ (toHtml title <> " — Індивідуальна робота")
    style_ css
  body_ $ do
    header_ [class_ "top"] $ do
      a_ [href_ "/", class_ "brand"] "🎓 Індивідуальна робота кафедри зі студентами"
      form_ [action_ "/search", method_ "get", class_ "gsearch"] $
        input_ [type_ "search", name_ "q", placeholder_ "Пошук по всій базі…"]
    div_ [class_ "wrap"] $ do
      nav_ [class_ "side"] $ do
        a_ [href_ "/"] "Головна"
        span_ [class_ "sep"] "Таблиці"
        forM_ allEntities $ \e -> a_ [href_ ("/t/" <> entityTable e)] (toHtml (entityPlural e))
        span_ [class_ "sep"] "Аналітика"
        a_ [href_ "/reports"] "Звіти"
      main_ $ do
        h1_ (toHtml title)
        body

------------------------------------------------------------------------------

dashboardPage :: [(SomeEntity, Int)] -> Html ()
dashboardPage counts = layout "Головна" $ do
  p_ [class_ "muted"] "Інформаційна система для ведення індивідуальної роботи викладачів кафедри зі студентами: теми та графік роботи, виконання завдань, допоміжні матеріали, питання студентів і відповіді викладачів."
  div_ [class_ "cards"] $ forM_ counts $ \(e, n) ->
    a_ [href_ ("/t/" <> entityTable e), class_ "card"] $ do
      div_ [class_ "num"] (toHtml (show n))
      div_ (toHtml (entityPlural e))
  h2_ "Звіти"
  reportList

reportList :: Html ()
reportList = ul_ [class_ "reports"] $ forM_ allReports $ \(SomeReport r) ->
  li_ $ do
    a_ [href_ ("/reports/" <> reportSlug r)] (toHtml (reportTitle r))
    span_ [class_ "muted"] (" — " <> toHtml (reportDescription r))

------------------------------------------------------------------------------

flashText :: Maybe Text -> Maybe Text
flashText m = case m of
  Just "created" -> Just "Запис додано."
  Just "saved"   -> Just "Зміни збережено."
  Just "deleted" -> Just "Запис видалено."
  _              -> Nothing

listPage :: TableView -> Maybe Text -> Maybe Text -> Html ()
listPage tv mq mflash = layout (tvTitle tv) $ do
  forM_ (flashText mflash) $ \m -> div_ [class_ "flash ok"] (toHtml m)
  div_ [class_ "toolbar"] $ do
    form_ [method_ "get", action_ ("/t/" <> tvTable tv), class_ "search"] $ do
      input_ [type_ "search", name_ "q", value_ (fromMaybe "" mq), placeholder_ "Пошук у таблиці (у т.ч. за пов'язаними записами)"]
      button_ [type_ "submit"] "Знайти"
      when (maybe False (not . T.null) mq) $ a_ [href_ ("/t/" <> tvTable tv), class_ "btn ghost"] "Скинути"
    a_ [href_ ("/t/" <> tvTable tv <> "/new"), class_ "btn primary"] "+ Додати"
  p_ [class_ "muted"] ("Записів: " <> toHtml (show (length (tvRows tv))))
  dataTable tv True

dataTable :: TableView -> Bool -> Html ()
dataTable tv withActions
  | null (tvRows tv) = p_ [class_ "empty"] "Немає записів."
  | otherwise = div_ [class_ "scroll"] $ table_ $ do
      thead_ $ tr_ $ do
        th_ "№"
        forM_ shown $ \(_, f) -> th_ (toHtml (fieldLabel f))
        when withActions $ th_ ""
      tbody_ $ forM_ (tvRows tv) $ \(i, vals) -> tr_ $ do
        td_ [class_ "muted"] (toHtml (show i))
        forM_ shown $ \(k, f) -> td_ (cell tv f (vals !! k))
        when withActions $ td_ [class_ "actions"] $ do
          a_ [href_ (rowUrl i <> "/edit"), class_ "btn small"] "Редагувати"
          form_ [method_ "post", action_ (rowUrl i <> "/delete"), class_ "inline",
                 onsubmit_ "return confirm('Видалити запис? Пов\\'язані записи також можуть бути видалені.')"] $
            button_ [type_ "submit", class_ "btn small danger"] "Видалити"
  where
    shown = [ (k, f) | (k, f) <- zip [0 ..] (tvFields tv), fieldInList f ]
    rowUrl i = "/t/" <> tvTable tv <> "/" <> T.pack (show i)

cell :: TableView -> Field -> MySQLValue -> Html ()
cell _ _ MySQLNull = span_ [class_ "muted"] "—"
cell tv f v = case fieldType f of
  FRef rt ->
    let key = either (const 0) id (fromDb v) :: Int
        lbl = fromMaybe ("#" <> valueText v) (lookup key (M.findWithDefault [] (fieldName f) (tvRefs tv)))
    in a_ [href_ ("/t/" <> rt <> "/" <> T.pack (show key) <> "/edit")] (toHtml lbl)
  FEnum _   -> span_ [class_ ("badge " <> badgeClass (valueText v))] (toHtml (valueText v))
  FLongText -> toHtml (let t = valueText v in if T.length t > 120 then T.take 117 t <> "…" else t)
  FText | "http" `T.isPrefixOf` valueText v -> a_ [href_ (valueText v), target_ "_blank"] (toHtml (valueText v))
  _         -> toHtml (displayValue v)

badgeClass :: Text -> Text
badgeClass t
  | t `elem` ["Зараховано", "Завершено"]             = "green"
  | t `elem` ["На доопрацюванні", "Скасовано"]       = "red"
  | t `elem` ["Здано", "В роботі", "В процесі"]       = "blue"
  | otherwise                                        = "gray"

------------------------------------------------------------------------------

-- | Форма введення / коригування запису.
formPage :: Text -> Text -> [Field] -> Map Text [(Int, Text)] -> Map Text Text -> [Text] -> Text -> Html ()
formPage table heading fs refs vals errs actionUrl = layout heading $ do
  unless (null errs) $ div_ [class_ "flash err"] $ ul_ $ forM_ errs (li_ . toHtml)
  form_ [method_ "post", action_ actionUrl, class_ "edit"] $ do
    forM_ fs $ \f -> div_ [class_ "row"] $ do
      label_ [for_ (fieldName f)] $ do
        toHtml (fieldLabel f)
        when (fieldRequired f) $ span_ [class_ "req"] " *"
      field f (M.findWithDefault "" (fieldName f) vals)
    div_ [class_ "buttons"] $ do
      button_ [type_ "submit", class_ "btn primary"] "Зберегти"
      a_ [href_ ("/t/" <> table), class_ "btn ghost"] "Скасувати"
  where
    reqAttr f = [required_ "required" | fieldRequired f]
    base f = [name_ (fieldName f), id_ (fieldName f)] ++ reqAttr f
    field f v = case fieldType f of
      FText     -> input_ (base f ++ [type_ "text", value_ v])
      FLongText -> textarea_ (base f ++ [rows_ "5"]) (toHtml v)
      FInt      -> input_ (base f ++ [type_ "number", value_ v])
      FDate     -> input_ (base f ++ [type_ "date", value_ v])
      FTime     -> input_ (base f ++ [type_ "time", value_ v])
      FDateTime -> input_ (base f ++ [type_ "datetime-local", value_ v])
      FEnum opts -> select_ (base f) $ do
        unless (fieldRequired f) $ option_ [value_ ""] "—"
        forM_ opts $ \o -> option_ ([value_ o] ++ [selected_ "selected" | o == v]) (toHtml o)
      FRef _ -> select_ (base f) $ do
        option_ [value_ ""] (if fieldRequired f then "— оберіть —" else "—")
        forM_ (M.findWithDefault [] (fieldName f) refs) $ \(i, l) ->
          let iv = T.pack (show i)
          in option_ ([value_ iv] ++ [selected_ "selected" | iv == v]) (toHtml l)

------------------------------------------------------------------------------

searchPage :: Text -> [TableView] -> Html ()
searchPage q tvs = layout ("Пошук: «" <> q <> "»") $ do
  let found = filter (not . null . tvRows) tvs
  when (null found) $ p_ [class_ "empty"] "Нічого не знайдено."
  forM_ found $ \tv -> do
    h2_ $ do
      a_ [href_ ("/t/" <> tvTable tv <> "?q=" <> q)] (toHtml (tvTitle tv))
      span_ [class_ "muted"] (" (" <> toHtml (show (length (tvRows tv))) <> ")")
    dataTable tv True

reportsPage :: Html ()
reportsPage = layout "Звіти" reportList

reportPage :: Report r => r -> [[MySQLValue]] -> Html ()
reportPage r rows = layout (reportTitle r) $ do
  p_ [class_ "muted"] (toHtml (reportDescription r))
  if null rows
    then p_ [class_ "empty"] "Даних немає."
    else div_ [class_ "scroll"] $ table_ $ do
      let hs = reportHeaders r
          hasAct = any (maybe False (const True) . rowAction r) rows
      thead_ $ tr_ $ do
        forM_ hs (th_ . toHtml)
        when hasAct $ th_ ""
      tbody_ $ forM_ rows $ \vals -> tr_ $ do
        forM_ (take (length hs) vals) (td_ . toHtml . displayValue)
        when hasAct $ td_ $ forM_ (rowAction r vals) $ \(lbl, url) ->
          a_ [href_ url, class_ "btn small"] (toHtml lbl)

messagePage :: Text -> Text -> Html ()
messagePage title msg = layout title $ do
  div_ [class_ "flash err"] (toHtml msg)
  p_ $ a_ [href_ "javascript:history.back()", class_ "btn ghost"] "← Назад"

------------------------------------------------------------------------------

css :: Text
css = T.unlines
  [ ":root{--bg:#f5f6fa;--panel:#fff;--text:#1e2330;--muted:#6b7280;--line:#e3e6ee;--accent:#3b5bdb;--accent2:#e7ecff;--danger:#c92a2a;--ok:#2b8a3e}"
  , "@media (prefers-color-scheme:dark){:root{--bg:#14161c;--panel:#1d2029;--text:#e6e8ee;--muted:#9aa1b1;--line:#2c313d;--accent:#7a94ff;--accent2:#262d45;--danger:#ff6b6b;--ok:#51cf66}}"
  , "*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text)}"
  , "a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}"
  , ".top{display:flex;gap:16px;align-items:center;justify-content:space-between;padding:12px 20px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}"
  , ".brand{font-weight:600;color:var(--text)}.gsearch input{width:min(340px,50vw)}"
  , ".wrap{display:flex;min-height:calc(100vh - 58px)}"
  , ".side{width:220px;flex:none;padding:16px 10px;border-right:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column;gap:2px}"
  , ".side a{padding:7px 10px;border-radius:6px;color:var(--text)}.side a:hover{background:var(--accent2);text-decoration:none}"
  , ".sep{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:14px 10px 4px}"
  , "main{flex:1;padding:20px 28px;min-width:0}h1{margin:0 0 14px;font-size:24px}h2{font-size:18px;margin:26px 0 10px}"
  , ".muted{color:var(--muted)}.empty{color:var(--muted);padding:24px;text-align:center;background:var(--panel);border:1px dashed var(--line);border-radius:10px}"
  , ".cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin:18px 0}"
  , ".card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;color:var(--text)}.card:hover{border-color:var(--accent);text-decoration:none}"
  , ".num{font-size:28px;font-weight:700;color:var(--accent)}"
  , ".reports li{margin:6px 0}"
  , ".toolbar{display:flex;gap:10px;justify-content:space-between;align-items:center;flex-wrap:wrap}.search{display:flex;gap:8px;flex:1;max-width:620px}.search input{flex:1}"
  , "input,select,textarea{font:inherit;color:inherit;background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:7px 10px}"
  , "input:focus,select:focus,textarea:focus{outline:2px solid var(--accent2);border-color:var(--accent)}"
  , "button,.btn{font:inherit;cursor:pointer;display:inline-block;border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:7px;padding:7px 14px}"
  , ".btn:hover,button:hover{text-decoration:none;border-color:var(--accent)}"
  , ".primary{background:var(--accent);border-color:var(--accent);color:#fff}.ghost{background:transparent}"
  , ".danger{color:var(--danger)}.small{padding:3px 9px;font-size:13px}"
  , ".scroll{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}"
  , "table{border-collapse:collapse;width:100%}th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}"
  , "th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);white-space:nowrap}tbody tr:hover{background:var(--accent2)}"
  , ".actions{white-space:nowrap}.inline{display:inline;margin-left:6px}"
  , ".badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;white-space:nowrap;background:var(--line)}"
  , ".badge.green{background:#d3f9d8;color:#2b8a3e}.badge.red{background:#ffe3e3;color:#c92a2a}.badge.blue{background:#dbe4ff;color:#364fc7}"
  , ".edit{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;max-width:720px}"
  , ".row{display:flex;flex-direction:column;gap:5px;margin-bottom:14px}.row label{font-weight:500}.req{color:var(--danger)}"
  , ".buttons{display:flex;gap:10px;margin-top:6px}"
  , ".flash{padding:10px 14px;border-radius:8px;margin-bottom:14px}.flash.ok{background:#d3f9d8;color:#2b8a3e}.flash.err{background:#ffe3e3;color:#c92a2a}.flash ul{margin:0;padding-left:18px}"
  , "@media (max-width:760px){.wrap{flex-direction:column}.side{width:auto;flex-direction:row;flex-wrap:wrap;border-right:0;border-bottom:1px solid var(--line)}.sep{display:none}main{padding:16px}.top{flex-direction:column;align-items:stretch}.gsearch input{width:100%}}"
  ]
