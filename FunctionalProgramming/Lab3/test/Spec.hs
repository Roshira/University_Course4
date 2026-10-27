module Main (main) where

import Prelude hiding (Word)
import Control.Monad (unless)
import System.Exit (exitFailure)
import System.IO (hSetEncoding, stdout, utf8)
import Text.Parser
import Text.Task
import Text.Types

check :: String -> Bool -> IO Bool
check name ok = do
  putStrLn ((if ok then "[OK]   " else "[FAIL] ") ++ name)
  pure ok

wordsOf :: String -> [String]
wordsOf = map wordString . textWords . parseText

sentencesOf :: String -> [String]
sentencesOf s = let Text ss = parseText s in map renderSentence ss

main :: IO ()
main = do
  hSetEncoding stdout utf8
  rs <- sequence
    [ check "класифікація символів" $
        map classify "я7 ,'+" == [Letter 'я', Digit '7', Space, Punct ',', Joiner '\'', Other '+']
    , check "табуляції та послідовності пробілів -> один пробіл" $
        sentencesOf "Це\t\t  тест   тексту." == ["Це тест тексту."]
    , check "поділ на речення (. ! ?), крапка в 3.14 і obj.f не ділить" $
        sentencesOf "Перше речення. Друге!  Третє? Число 3.14 і obj.f тут." ==
          ["Перше речення.", "Друге!", "Третє?", "Число 3.14 і obj.f тут."]
    , check "апостроф і дефіс усередині слова" $
        wordsOf "Об'єкт будь-який, 'лапки' - тире." == ["Об'єкт", "будь-який", "лапки", "тире"]
    , check "українська абетка: г < ґ < д, е < є < ж, и < і < ї < й" $
        map wordString (sortedWords True (parseText "й ї і и ж є е д ґ г"))
          == ["г", "ґ", "д", "е", "є", "ж", "и", "і", "ї", "й"]
    , check "без урахування регістру, без повторень, без чисел" $
        map wordString (sortedWords True (parseText "Бета альфа АЛЬФА 42 бета Альфа."))
          == ["альфа", "Бета"]
    , check "режим --all залишає повтори" $
        length (sortedWords False (parseText "а б а А")) == 4
    , check "латиниця перед кирилицею" $
        map wordString (sortedWords True (parseText "мова Haskell map функція"))
          == ["Haskell", "map", "мова", "функція"]
    , check "групування за першою літерою" $
        map (\(c, ws) -> (c, map wordString ws))
            (groupByFirstLetter (sortedWords True (parseText "кіт ага кава Абетка бук")))
          == [('а', ["Абетка", "ага"]), ('б', ["бук"]), ('к', ["кава", "кіт"])]
    , check "кожна нова літера — з червоного рядка (відступ 4)" $
        formatGroups 4 80 (groupByFirstLetter (sortedWords True (parseText "бук ага кава")))
          == ["    ага", "    бук", "    кава"]
    , check "перенесення довгого абзацу без відступу" $
        formatGroups 4 14 (groupByFirstLetter (sortedWords True (parseText "аа аб ав аг ад")))
          == ["    аа аб ав", "аг ад"]
    ]
  unless (and rs) exitFailure
  putStrLn "Усі тести пройдено."
