module Main (main) where

import           Data.Maybe         (fromMaybe)
import           System.Environment (lookupEnv)
import           System.IO
import           Text.Read          (readMaybe)

import           Db                 (loadConnectInfo)
import           Web.Server         (runServer)

main :: IO ()
main = do
  hSetEncoding stdout utf8
  ci   <- loadConnectInfo
  port <- fromMaybe 3000 . (>>= readMaybe) <$> lookupEnv "PORT"
  putStrLn ("Сервер запущено: http://localhost:" ++ show port)
  runServer port ci
