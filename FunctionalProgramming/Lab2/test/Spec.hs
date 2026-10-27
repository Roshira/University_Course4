module Main (main) where

import Batcher
import Control.Monad (forM, unless)
import Data.List (sort, nub)
import System.Exit (exitFailure)
import System.IO (hSetEncoding, stdout, utf8)

lcg :: Int -> [Int]
lcg = tail . iterate (\x -> (x * 1103515245 + 12345) `mod` 2147483648)

check :: String -> Bool -> IO Bool
check name ok = do
  putStrLn ((if ok then "[OK]   " else "[FAIL] ") ++ name)
  pure ok

main :: IO ()
main = do
  hSetEncoding stdout utf8
  -- 1. Компаратори одного етапу не перетинаються (умова паралельності).
  r1 <- check "компаратори кожного етапу не перетинаються (n = 1..70)" $
    and [ let cs = comparatorsOf n st
              ixs = concat [ [a, b] | (a, b) <- cs ]
          in length ixs == length (nub ixs)
        | n <- [1 .. 70], st <- stages n ]

  -- 2. Принцип 0-1: мережа сортує всі 0-1 послідовності => сортує будь-які.
  r2 <- check "принцип 0-1: усі 0/1-масиви довжини 1..14 сортуються" $
    and [ applyNet n xs == sort xs
        | n <- [1 .. 14], m <- [0 .. 2 ^ n - 1 :: Int]
        , let xs = [ (m `div` (2 ^ i)) `mod` 2 | i <- [0 .. n - 1] ] ]

  -- 3. Паралельне сортування випадкових масивів різних розмірів і k.
  rs <- forM [ (n, k) | n <- [0, 1, 2, 3, 5, 7, 8, 13, 100, 257, 1000, 4097, 50000]
                      , k <- [1, 2, 3, 4, 7, 16] ] $ \(n, k) -> do
    let xs = map (`mod` 1000) (take n (lcg (n * 31 + k)))
    ys <- sortListPar k xs
    pure (ys == sort xs, (n, k))
  let bad = [ nk | (False, nk) <- rs ]
  r3 <- check ("випадкові масиви, " ++ show (length rs) ++ " комбінацій (n, k)") (null bad)
  unless (null bad) $ print bad

  -- 4. Крайні випадки: вже відсортований, обернений, усі однакові, від'ємні.
  let cases = [ [1 .. 1000], [1000, 999 .. 1], replicate 500 7, [5, -3, 0, -100, 42, 42, -3] ]
  r4 <- fmap and $ forM cases $ \xs -> (== sort xs) <$> sortListPar 4 xs
  _ <- check "крайні випадки (відсортований, обернений, однакові, від'ємні)" r4

  unless (and [r1, r2, r3, r4]) exitFailure
  putStrLn "Усі тести пройдено."
  where
    applyNet n xs = foldl step xs (stages n)
      where step v st = foldl swap v (comparatorsOf n st)
            swap v (a, b) | v !! a > v !! b = [ pick i x | (i, x) <- zip [0 ..] v ]
                          | otherwise = v
              where pick i x | i == a = v !! b
                             | i == b = v !! a
                             | otherwise = x
