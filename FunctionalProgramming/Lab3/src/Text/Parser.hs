-- | Розбір рядка у 'Text': символи -> лексеми -> речення.
module Text.Parser
  ( classify
  , tokenize
  , splitSentences
  , parseText
  ) where

import Prelude hiding (Word)
import Data.Char (isAlpha, isDigit, isSpace, isPunctuation)
import Text.Types

-- | Класифікація символу.
classify :: Char -> Symbol
classify c
  | isAlpha c          = Letter c
  | isDigit c          = Digit c
  | isSpace c          = Space
  | c `elem` joiners   = Joiner c
  | isPunctuation c    = Punct c
  | otherwise          = Other c

joiners :: String
joiners = "'’ʼ-"

isWordSym :: Symbol -> Bool
isWordSym s = case s of
  Letter _ -> True
  Digit _  -> True
  _        -> False

-- | Розбити послідовність символів на лексеми.
--   Апостроф/дефіс входить у слово лише між двома літерами/цифрами.
--   Послідовності пробілів і табуляцій стискаються в один 'Gap'.
tokenize :: [Symbol] -> [Token]
tokenize [] = []
tokenize (Space : rest) = Gap : tokenize (dropWhile (== Space) rest)
tokenize ss@(s : rest)
  | isWordSym s = let (w, rest') = takeWord ss in TWord (Word w) : tokenize rest'
  | otherwise   = TPunct (Punctuation (symbolChar s)) : tokenize rest
  where
    takeWord xs = case span isWordSym xs of
      (w, j@(Joiner _) : y : more) | isWordSym y ->
        let (w', r) = takeWord (y : more) in (w ++ [j] ++ w', r)
      res -> res

-- | Поділ лексем на речення: речення закінчується на '.', '!', '?', '…'
--   (разом з наступними закривними знаками), за якими йде пробіл або кінець тексту.
--   Крапка всередині "obj.field" чи "3.14" речення не завершує.
splitSentences :: [Token] -> [Sentence]
splitSentences = filter nonEmpty . map (Sentence . trim) . go []
  where
    go acc [] = [reverse acc | not (null acc)]
    go acc (t : ts)
      | isEnd t =
          let (closers, rest) = span isCloser ts
              acc' = reverse closers ++ t : acc
          in case rest of
               []         -> [reverse acc']
               (Gap : _)  -> reverse acc' : go [] rest
               _          -> go acc' rest
      | otherwise = go (t : acc) ts

    isEnd (TPunct (Punctuation c)) = c `elem` ".!?…"
    isEnd _ = False
    isCloser (TPunct (Punctuation c)) = c `elem` ".!?…\"»)'’"
    isCloser _ = False

    trim = reverse . dropWhile (== Gap) . reverse . dropWhile (== Gap)
    nonEmpty (Sentence ts) = not (null ts)

parseText :: String -> Text
parseText = Text . splitSentences . tokenize . map classify
