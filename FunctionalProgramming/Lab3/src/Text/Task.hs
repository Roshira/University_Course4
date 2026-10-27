-- | Варіант 6: надрукувати слова тексту в алфавітному порядку за першою
--   літерою; слова, що починаються з нової літери, друкувати з червоного рядка.
module Text.Task
  ( alphabetKey
  , compareWords
  , sortedWords
  , groupByFirstLetter
  , formatGroups
  ) where

import Prelude hiding (Word)
import Data.Char (toLower, isDigit)
import Data.Function (on)
import Data.List (sortBy, groupBy, nubBy, elemIndex)
import Data.Maybe (fromMaybe)
import Text.Types

-- | Порядок літер: цифри, латиниця, українська абетка (з ґ, є, і, ї),
--   далі літери, яких немає в українській абетці (ё, ъ, ы, э).
alphabet :: String
alphabet = ['0' .. '9'] ++ ['a' .. 'z'] ++ "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя" ++ "ёъыэ"

-- | Ключ символу для сортування (без урахування регістру).
--   Невідомі символи йдуть після відомих, у порядку кодів Unicode.
alphabetKey :: Char -> (Int, Char)
alphabetKey c =
  let l = toLower c
  in (fromMaybe (length alphabet) (elemIndex l alphabet), l)

wordKey :: Word -> [(Int, Char)]
wordKey = map alphabetKey . filter (not . isJoiner) . wordString
  where isJoiner ch = ch `elem` "'’ʼ-"

-- | Порівняння слів за абеткою (регістр не враховується).
compareWords :: Word -> Word -> Ordering
compareWords a b = compare (wordKey a) (wordKey b) <> compare (wordString a) (wordString b)

-- | Слова тексту, впорядковані за абеткою.
--   unique = True — без повторень (однакові з точністю до регістру слова друкуються один раз).
--   Числа (слова лише з цифр) не враховуються.
sortedWords :: Bool -> Text -> [Word]
sortedWords unique txt =
  let ws  = filter (not . all isDigit . wordString) (textWords txt)
      ws' = if unique then nubBy ((==) `on` lowerStr) ws else ws
  in  sortBy compareWords ws'
  where lowerStr = map toLower . wordString

firstLetter :: Word -> Char
firstLetter = toLower . head . wordString

-- | Групи слів з однаковою першою літерою.
groupByFirstLetter :: [Word] -> [(Char, [Word])]
groupByFirstLetter ws =
  [ (firstLetter (head g), g) | g <- groupBy ((==) `on` firstLetter) ws ]

-- | Друк: кожна група (нова літера) — новий абзац з червоного рядка (відступ),
--   довгі абзаци переносяться по ширині без відступу.
formatGroups :: Int -> Int -> [(Char, [Word])] -> [String]
formatGroups indent width = concatMap paragraph
  where
    paragraph (_, ws) = wrap (replicate indent ' ') (map wordString ws)

    wrap line [] = [line]
    wrap line (w : rest)
      | all (== ' ') line          = wrap (line ++ w) rest
      | length line + 1 + length w <= width = wrap (line ++ " " ++ w) rest
      | otherwise                  = line : wrap w rest
